from maya import cmds, OpenMayaUI
from maya.api import OpenMaya
from .utils import chunk, closest_uv
import re

@chunk
def create_multi_skin(mesh, mesh_orig, layers_number, setup_name):
    print('create_multi_skin', mesh, mesh_orig, layers_number)

    mesh_skin_clusters = cmds.listConnections(f'{mesh}.inMesh', source=True, destination=False, type='skinCluster')
    if not mesh_skin_clusters:
        raise Exception(f'No skin cluster found on {mesh!r}')

    mesh_skin_cluster = mesh_skin_clusters[0]

    grp_name = f'{setup_name}_prx'
    if cmds.objExists(grp_name):
        raise Exception('Grp {grp!r} already exists.')
    grp = cmds.group(empty=True, world=True, name=grp_name)

    mesh_proxies = list()
    skin_clusters = list()
    for i in range(layers_number):
        layer_name = f'{setup_name}_d{i}'

        # msh prx
        mesh_trs_prx_name = f'{layer_name}_prx'
        mesh_trs_prx, = cmds.duplicate(mesh, name=mesh_trs_prx_name)

        mesh_trs_prx_meshes = cmds.listRelatives(mesh_trs_prx, shapes=True, type='mesh')
        mesh_prx = mesh_trs_prx_meshes[0]
        mesh_proxies.append(mesh_prx)

        cmds.parent(mesh_trs_prx, grp)

        # jnt
        cmds.select(clear=True)
        layer_joint = cmds.joint(name=f'{layer_name}_jnt')
        cmds.parent(layer_joint, grp)

        # skin cluster
        skin_cluster_name = f'{layer_name}_skinCluster'
        skin_cluster, = cmds.skinCluster(
            layer_joint,
            mesh_prx,
            name=skin_cluster_name,
            maximumInfluences=8,
            normalizeWeights=0,
            obeyMaxInfluences=False
        )
        skin_clusters.append(skin_cluster)

    mesh_proxies.reverse()
    skin_clusters.reverse()

    # connections
    for next_mesh_prx, skin_cluster in zip(mesh_proxies[1:], skin_clusters):
        cmds.connectAttr(f'{next_mesh_prx}.outMesh', f'{skin_cluster}.originalGeometry[0]', force=True)
        cmds.connectAttr(f'{next_mesh_prx}.outMesh', f'{skin_cluster}.input[0].inputGeometry', force=True)

    # cmds.connectAttr(f'{mesh_orig}.outMesh', f'{skin_clusters[-1]}.originalGeometry[0]', force=True)
    # cmds.connectAttr(f'{mesh_orig}.outMesh', f'{skin_clusters[-1]}.input[0].inputGeometry', force=True)
    #
    cmds.connectAttr(f'{mesh_proxies[0]}.outMesh', f'{mesh_skin_cluster}.originalGeometry[0]', force=True)
    cmds.connectAttr(f'{mesh_proxies[0]}.outMesh', f'{mesh_skin_cluster}.input[0].inputGeometry', force=True)


@chunk
def pin_ctrl(ctrl, skin_cluster):
    ctrl_name_split = ctrl.split('_')
    name = '_'.join(ctrl_name_split[:-1])

    # mesh
    meshes = list()
    for node in cmds.listHistory(f'{skin_cluster}.originalGeometry'):
        if cmds.objectType(node, isAType='mesh') and not cmds.getAttr(f'{node}.intermediateObject'):
            meshes.append(node)

    if len(meshes) < 2:
        raise Exception(f'Need at least two meshes connect to the skin cluster {skin_cluster!r}. Got {len(meshes)}')

    deformed_geometry = meshes[0]
    original_geometry = meshes[1]

    # ctrl parent
    ctrl_parents = cmds.listRelatives(ctrl, parent=True)

    if not ctrl_parents:
        raise Exception(f'No parent found for ctrl {ctrl!r}')

    ctrl_parent, = ctrl_parents

    # uv pin
    uv_pin = cmds.createNode('uvPin', name=f'{name}_pin')
    cmds.connectAttr(f'{deformed_geometry}.worldMesh[0]', f'{uv_pin}.deformedGeometry')
    cmds.connectAttr(f'{original_geometry}.worldMesh[0]', f'{uv_pin}.originalGeometry')

    uv_pin_loc, = cmds.spaceLocator(name=f'{name}_pin_loc')
    cmds.connectAttr(f'{uv_pin}.outputMatrix[0]', f'{uv_pin_loc}.offsetParentMatrix')

    point = cmds.xform(ctrl, translation=True, worldSpace=True, q=True)
    u, v = closest_uv(deformed_geometry, point)

    cmds.setAttr(f'{uv_pin}.coordinate[0].coordinateU', u)
    cmds.setAttr(f'{uv_pin}.coordinate[0].coordinateV', v)

    cmds.pointConstraint(uv_pin_loc, ctrl_parent, maintainOffset=True)


@chunk
def pin_selected_facial_ctrls():
    selection = cmds.ls(sl=True)

    for node in selection:
        pin_ctrl(node)


@chunk
def connect_pre_bind_matrix(ctrl):
    # joint
    joints = cmds.listRelatives(ctrl, children=True, type='joint') or list()

    if len(joints) != 1:
        raise Exception(f'Need exactly one joint under the ctrl. Got {len(joints)}')

    joint, = joints

    # ctrl parent
    ctrl_parents = cmds.listRelatives(ctrl, parent=True)

    if not ctrl_parents:
        raise Exception(f'No parent found for ctrl {ctrl!r}')

    ctrl_parent, = ctrl_parents

    # skin cluster
    skin_cluster_plugs = cmds.listConnections(
        f'{joint}.worldMatrix[0]',
        source=False,
        destination=True,
        plugs=True,
        type='skinCluster'
    ) or list()

    for skin_cluster_plug in skin_cluster_plugs:
        skin_cluster, skin_cluster_attr = skin_cluster_plug.split('.')

        skin_cluster_index = re.findall(r'\d+', skin_cluster_attr)[0]

        try:
            cmds.connectAttr(
                f'{ctrl_parent}.worldInverseMatrix[0]',
                f'{skin_cluster}.bindPreMatrix[{skin_cluster_index}]',
            )
        except Exception as e:
            cmds.warning(e)


@chunk
def connect_pre_bind_matrix_on_selected():
    selection = cmds.ls(sl=True, type='transform')

    for transform in selection:
        connect_pre_bind_matrix(transform)


@chunk
def set_vertex_on_pin_facial(vertex, ctl):
    position = cmds.xform(vertex, q=True, translation=True, worldSpace=True)

    vertex_split = vertex.split('.')
    mesh = vertex_split[0]

    u, v = closest_uv(mesh, position)

    bfr, = cmds.listRelatives(ctl, parent=True)
    bfr_matrix = cmds.xform(bfr, q=True, matrix=True, worldSpace=True)

    history = cmds.listHistory(bfr)
    print(ctl, history)
    point_constraint, = [x for x in history if cmds.objectType(x, isAType='pointConstraint')]
    loc, = [x for x in history if x.endswith('_pin_loc')]
    uv_pin, = [x for x in cmds.listConnections(loc, source=True, destination=False) or list() if cmds.objectType(x, isAType='uvPin')]

    cmds.delete(point_constraint)

    cmds.setAttr(f'{uv_pin}.coordinate[0].coordinateU', u)
    cmds.setAttr(f'{uv_pin}.coordinate[0].coordinateV', v)

    cmds.pointConstraint(loc, bfr, maintainOffset=True)

    cmds.xform(bfr, matrix=bfr_matrix, worldSpace=True)


@chunk
def set_vertex_on_selected_pin_facial():
    vertex, ctl = cmds.ls(sl=True)
    set_vertex_on_pin_facial(vertex, ctl)


@chunk
def disconnect_pre_bin_on_selected():
    selection = cmds.ls(sl=True, type='transform')

    for ctrl in selection:
        ctrl_info = get_ctrl_info(ctrl)
        ctrl_bfr = ctrl_info['bfr']

        ctrl_bfr_plug = f'{ctrl_bfr}.worldInverseMatrix[0]'
        ctrl_bfr_matrix = cmds.getAttr(ctrl_bfr_plug)

        skin_clusters_plugs = cmds.listConnections(
            ctrl_bfr_plug,
            source=False,
            destination=True,
            plugs=True,
            type='skinCluster'
        )

        print(ctrl_bfr, skin_clusters_plugs)
        if not skin_clusters_plugs:
            continue

        for skin_clusters_plug in skin_clusters_plugs:
            cmds.disconnectAttr(ctrl_bfr_plug, skin_clusters_plug)
            cmds.setAttr(skin_clusters_plug, ctrl_bfr_matrix, type='matrix')


def get_ctrl_info(ctrl):
    # bfr
    bfr, = cmds.listRelatives(ctrl, parent=True)

    # joint
    joints = cmds.listRelatives(ctrl, children=True, type='joint') or list()

    if joints:
        joint, = joints

        # skin cluster
        skin_clusters = cmds.listConnections(
            f'{joint}.worldMatrix[0]',
            source=False,
            destination=True,
            type='skinCluster'
        ) or list()
    else:
        joint = str()
        skin_clusters = list()

    data = {
        'bfr': bfr,
        'joint': joint,
        'skin_clusters': skin_clusters
    }
    return data


def get_all_multi_skin_info():
    d_zero_skin_clusters = cmds.ls('*_d0_skinCluster', type='skinCluster')

    all_info = dict()

    for d_zero_skin_cluster in d_zero_skin_clusters:
        d_zero_name_split = d_zero_skin_cluster.split('_')
        d_zero_name_split.pop()
        d_zero_name_split.pop()

        setup_name = '_'.join(d_zero_name_split)

        history = cmds.listHistory(d_zero_skin_cluster, future=True)
        meshes = [x for x in history if cmds.objectType(x, isAType='mesh')]
        skin_clusters = [x for x in history if cmds.objectType(x, isAType='skinCluster')]

        orig_mesh = meshes.pop()
        orig_skin_cluster = skin_clusters.pop()

        all_info[setup_name] = {
            'orig_mesh': orig_mesh,
            'orig_skin_cluster': orig_skin_cluster,
            'meshes': meshes,
            'skin_clusters': skin_clusters,
            'layer_count': len(meshes) - 1,
        }

    return all_info