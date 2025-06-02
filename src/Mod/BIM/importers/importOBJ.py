# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2011 Yorik van Havre <yorik@uncreated.net>              *
# *                                                                         *
# *   This file is part of FreeCAD.                                         *
# *                                                                         *
# *   FreeCAD is free software: you can redistribute it and/or modify it    *
# *   under the terms of the GNU Lesser General Public License as           *
# *   published by the Free Software Foundation, either version 2.1 of the  *
# *   License, or (at your option) any later version.                       *
# *                                                                         *
# *   FreeCAD is distributed in the hope that it will be useful, but        *
# *   WITHOUT ANY WARRANTY; without even the implied warranty of            *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU      *
# *   Lesser General Public License for more details.                       *
# *                                                                         *
# *   You should have received a copy of the GNU Lesser General Public      *
# *   License along with FreeCAD. If not, see                               *
# *   <https://www.gnu.org/licenses/>.                                      *
# *                                                                         *
# ***************************************************************************

## @package importOBJ
#  \ingroup BIM
#  \brief OBJ file format importer
#
#  This module provides tools to import OBJ files.
#  It is an alternative to the standard Mesh OBJ importer
#  and supports importing faces with more than 3 vertices
#  and supports object colors / materials

import codecs
import ntpath
import os
from builtins import open as pyopen

import FreeCAD
import Arch
import Draft
import DraftGeomUtils
import Mesh
import MeshPart
import Part

from draftutils import params

if FreeCAD.GuiUp:
    from draftutils.translate import translate
else:
    # \cond
    def translate(context,text):
        return text
    # \endcond


# return entry after given index from an array or None on array end
def peek(index, array):
    if index < len(array) - 1:
        return array[index+1].strip()
    else:
        return None

def open(filename):
    "called when freecad wants to open a file"
    docname = os.path.splitext(os.path.basename(filename))[0]
    doc = FreeCAD.newDocument(docname)
    doc.Label = docname
    return insert(filename,doc.Name)

def insert(filename,docname):

    meshName = ntpath.basename(filename)
    for i in meshName.split():
        if "." in i:
            i = i.split(".")[0]
    meshName = i
    group = None
    "called when freecad wants to import a file"
    try:
        doc = FreeCAD.getDocument(docname)
        group = doc.addObject("App::DocumentObjectGroup", meshName)
    except NameError:
        doc = FreeCAD.newDocument(docname)
    FreeCAD.ActiveDocument = doc

    with pyopen(filename,"r",encoding="utf8") as infile:
        verts = []
        medges = []
        edges = []
        facets = []
        activeobject = None
        material = None
        colortable = {}
        content_array = []
        for line in infile:
            line = line.strip()
            while line.endswith('\\'):
                next_line = next(infile).strip()
                line = line.rstrip()[:-1] + ' ' + next_line
            content_array.append(line)
    activeobjectExists = False
    for line in content_array:
        if line[:2] == "o ":
            activeobjectExists = True
    if not activeobjectExists:
        activeobject = meshName
    for index, line in enumerate(content_array):
        if line[:7] == "mtllib ":
            matlib = os.path.join(os.path.dirname(filename),line[7:])
            if os.path.exists(matlib):
                with pyopen(matlib,"r") as matfile:
                    mname = None
                    color = None
                    trans = None
                    for mline in matfile:
                        mline = mline.strip()
                        if mline[:7] == "newmtl ":
                            if mname and color:
                                colortable[mname] = [color,trans]
                            color = None
                            trans = None
                            mname = mline[7:]
                        elif mline[:3] == "Kd ":
                            color = tuple([float(i) for i in mline[3:].split()])
                        elif mline[:2] == "d ":
                            trans = int((1-float(mline[2:]))*100)
                    if mname and color:
                        colortable[mname] = [color,trans]
        elif line[:2] == "o ":
            if activeobject:
                makeMesh(doc,group,activeobject,verts,medges,facets,material,colortable)
            material = None
            medges = []
            facets = []
            activeobject = line[2:]
        elif line[:2] == "v ":
            verts.append([float(i) for i in line[2:].split()])
        elif line[:2] == "f ":
            fa = []
            for i in line[2:].split():
                if "/" in i:
                    i = i.split("/")[0]
                fa.append(int(i))
            facets.append(fa)
        elif line[:2] == "l ":
            edge = []
            for i in line[2:].split():
                if "/" in i:
                    i = i.split("/")[0]
                edge.append(int(i))
            edges.append(edge)
            # combine lines into medges
            l = peek(index, content_array)
            if l == None or l[:2] != "l ":
                medges = edges
                edges = []
        elif line[:7] == "usemtl ":
            material = line[7:]
    if activeobject:
        makeMesh(doc,group,activeobject,verts,medges,facets,material,colortable)
    FreeCAD.Console.PrintMessage(translate("BIM","Successfully imported") + ' ' + filename + "\n")
    return doc

def makeMesh(doc,group,activeobject,verts,edges,facets,material,colortable):
    mfacets = []
    if facets:
        for facet in facets:
            if len(facet) > 3:
                vecs = [FreeCAD.Vector(*verts[i-1]) for i in facet]
                vecs.append(vecs[0])
                pol = Part.makePolygon(vecs)
                try:
                    face = Part.Face(pol)
                except Part.OCCError:
                    print("Skipping non-planar polygon:",vecs)
                else:
                    tris = face.tessellate(1)
                    for tri in tris[1]:
                        mfacets.append([tris[0][i] for i in tri])
            else:
                mfacets.append([verts[i-1] for i in facet])
    if mfacets:
        mobj = doc.addObject("Mesh::Feature",activeobject)
        mobj.Label = activeobject
        mobj.Mesh = Mesh.Mesh(mfacets)
        if FreeCAD.GuiUp and material and material in colortable:
            mobj.ViewObject.ShapeColor = colortable[material][0]
            if colortable[material][1] is not None:
                mobj.ViewObject.Transparency = colortable[material][1]
        if group:
            group.addObjects([mobj])

    # make polylines from edges
    medges = []
    if edges:
        polyline = []
        for edge in edges:
            # single line
            if len(edge) == 2:
                i1 = edge[0]
                i2 = edge[1]
                if i1 == i2:
                    continue
                if len(polyline) > 0:
                    if polyline[-1] == i1:
                        polyline.append(i2)
                    else:
                        medges.append(polyline)
                        polyline = []
                        polyline.append(i1)
                        polyline.append(i2)
                else:
                    polyline.append(i1)
                    polyline.append(i2)
            else:
                medges.append(edge)
        if len(polyline) > 0:
            medges.append(polyline)
    if medges:
        part = doc.addObject("App::Part", activeobject)
        part.Label = activeobject
        features = []
        for strip in medges:
            points = [FreeCAD.Vector(*verts[i-1]) for i in strip]
            wire = Draft.make_wire(points)
            if FreeCAD.GuiUp and material and material in colortable:
                wire.ViewObject.ShapeColor = colortable[material][0]
                if colortable[material][1] is not None:
                    wire.ViewObject.Transparency = colortable[material][1]
            features.append(wire)
        part.addObjects(features)
        if group:
            group.addObjects([part])

    doc.recompute()
