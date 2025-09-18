from maya import cmds, OpenMayaUI
from maya.api import OpenMaya

try:
    from PySide6.QtWidgets import *
    from shiboken6 import wrapInstance
except ModuleNotFoundError:
    from PySide2.QtWidgets import *
    from shiboken2 import wrapInstance

class Chunk(object):

    def __init__(self, name='untitled'):
        self.name = str(name)

    def __enter__(self):
        cmds.undoInfo(openChunk=True, chunkName=self.name)

    def __exit__(self, exc_type, exc_val, exc_tb):
        cmds.undoInfo(closeChunk=True)

def chunk(func):
    def wrapper(*args, **kwargs):
        with Chunk(name=func.__name__):
            return func(*args, **kwargs)

    return wrapper

def get_maya_main_window():
    pointer = OpenMayaUI.MQtUtil.mainWindow()
    return wrapInstance(int(pointer), QMainWindow)

def closest_uv(mesh, world_point):
    sel = OpenMaya.MSelectionList()
    sel.add(mesh)

    dag = sel.getDagPath(0)
    fn_mesh = OpenMaya.MFnMesh(dag)

    point = OpenMaya.MPoint(world_point[0], world_point[1], world_point[2])
    closest_point, face_idx = fn_mesh.getClosestPoint(point, OpenMaya.MSpace.kWorld)

    u, v, _ = fn_mesh.getUVAtPoint(closest_point, OpenMaya.MSpace.kWorld)
    return u, v