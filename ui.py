try:
    from PySide6.QtCore import *
    from PySide6.QtWidgets import *
except ModuleNotFoundError:
    from PySide2.QtCore import *
    from PySide2.QtWidgets import *


from .core import create_multi_skin, connect_pre_bind_matrix_on_selected, pin_selected_facial_ctrls, \
    set_vertex_on_selected_pin_facial, pin_ctrl, get_ctrl_info, disconnect_pre_bin_on_selected, get_all_multi_skin_info
from .utils import get_maya_main_window, chunk

from maya import cmds


class ComboDialog(QDialog):

    def __init__(self, parent):
        super().__init__(parent)

        self.resize(500, 500)

        self.items = list()

        self.combo = QComboBox()

        ok_btn = QPushButton('Ok')
        ok_btn.clicked.connect(self.accept)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.combo)
        main_layout.addStretch()
        main_layout.addWidget(ok_btn, alignment=Qt.AlignmentFlag.AlignRight)

    def reload(self):
        self.combo.clear()

        for item in self.items:
            self.combo.addItem(str(item), userData=item)

    def get_item(self):
        item = self.combo.currentData(Qt.ItemDataRole.UserRole)
        return item


class MultiSkinEditor(QDialog):
    def __init__(self, parent=None):
        if parent is None:
            parent = get_maya_main_window()
        super().__init__(parent)

        self.setWindowTitle('Multi-Skin Editor')
        self.resize(500, 500)

        create_btn = QPushButton('Create')
        create_btn.clicked.connect(self.create)

        self.layers_number_spin = QSpinBox()
        self.layers_number_spin.setFixedWidth(150)
        self.layers_number_spin.setValue(5)

        self.setup_name_line = QLineEdit()
        self.setup_name_line.setFixedWidth(150)
        self.setup_name_line.setText('body')

        create_form_layout = QFormLayout()
        create_form_layout.addRow('Setup Name', self.setup_name_line)
        create_form_layout.addRow('Number of Layers', self.layers_number_spin)

        create_multi_skin_layout = QVBoxLayout()
        create_multi_skin_layout.addLayout(create_form_layout)
        create_multi_skin_layout.addWidget(create_btn, alignment=Qt.AlignmentFlag.AlignRight)

        self.display_combo = QComboBox()
        self.display_combo.currentIndexChanged.connect(self.display)

        display_layout = QVBoxLayout()
        display_layout.addWidget(self.display_combo)

        multi_skin_layout = QVBoxLayout()
        multi_skin_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        multi_skin_layout.addWidget(QLabel('Create'))
        multi_skin_layout.addLayout(create_multi_skin_layout)
        multi_skin_layout.addWidget(QLabel('Display'))
        multi_skin_layout.addLayout(display_layout)

        # pin
        pin_selected_ctrl_btn = QPushButton('Pin Selected Ctrl')
        pin_selected_ctrl_btn.clicked.connect(self.pin_selected_ctrls)

        edit_pin_vertex_btn = QPushButton('Edit Pin Vertex')
        edit_pin_vertex_btn.clicked.connect(set_vertex_on_selected_pin_facial)

        pin_layout = QVBoxLayout()
        pin_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        pin_layout.addWidget(pin_selected_ctrl_btn)
        pin_layout.addWidget(edit_pin_vertex_btn)

        # pre_bind
        connect_pre_bind_btn = QPushButton('Connect Pre-Bind')
        connect_pre_bind_btn.clicked.connect(connect_pre_bind_matrix_on_selected)

        disconnect_pre_bind_btn = QPushButton('Disconnect Pre-Bind')
        disconnect_pre_bind_btn.clicked.connect(disconnect_pre_bin_on_selected)

        pre_bind_layout = QVBoxLayout()
        pre_bind_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        pre_bind_layout.addWidget(connect_pre_bind_btn)
        pre_bind_layout.addWidget(disconnect_pre_bind_btn)

        # tabs
        tabs = {
            'multi-skin': multi_skin_layout,
            'pin': pin_layout,
            'pre-bind': pre_bind_layout,
        }

        tab = QTabWidget()
        for name, layout in tabs.items():
            widget = QWidget()
            widget.setLayout(layout)

            tab.addTab(widget, name)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(tab)

    @chunk
    def display(self, index):
        for i in range(self.display_combo.count()):
            meshes = self.display_combo.itemData(i, Qt.ItemDataRole.UserRole)

            mesh_transforms = [cmds.listRelatives(x, parent=True)[0] for x in meshes]

            if i == index:
                cmds.showHidden(mesh_transforms)
            else:
                cmds.hide(mesh_transforms)

    def reload(self):
        self.display_combo.clear()

        all_multi_skin_info = get_all_multi_skin_info()

        layers = {
            'result': list()
        }
        for setup_name, multi_skin_info in all_multi_skin_info.items():
            for index, mesh in enumerate(multi_skin_info['meshes']):
                index_str = f'd{index}'
                if not index_str in layers:
                    layers[index_str] = list()

                layers[index_str].append(mesh)

            layers['result'].append(multi_skin_info['orig_mesh'])

        for layer_name, layer_meshes in layers.items():
            self.display_combo.addItem(layer_name, userData=layer_meshes)

    @chunk
    def pin_selected_ctrls(self):
        selection = cmds.ls(sl=True, type='transform')

        for ctrl in selection:
            ctrl_skin_info = get_ctrl_info(ctrl)

            skin_clusters = ctrl_skin_info['skin_clusters']

            if len(skin_clusters) == 0:
                raise Exception(f'Ctrl {ctrl!r} is not connected to a skin cluster')
            elif len(skin_clusters) == 1:
                skin_cluster = skin_clusters[0]
            else:
                ui = ComboDialog(self)
                ui.setWindowTitle(f'Pin {ctrl!r}')

                ui.items = skin_clusters
                ui.reload()

                proceed = ui.exec()

                if not proceed:
                    print(f'Ctrl {ctrl!r} skipped!')
                    continue

                skin_cluster = ui.get_item()

            pin_ctrl(ctrl, skin_cluster=skin_cluster)

    @chunk
    def create(self):
        selection = cmds.ls(sl=True, type='transform')
        layers_number = self.layers_number_spin.value()

        setup_name = self.setup_name_line.text()

        for node in selection:
            meshes = cmds.listRelatives(node, shapes=True, type='mesh') or list()

            mesh = None
            mesh_orig = None

            for x in meshes:
                if x.endswith('Shape'):
                    mesh = x
                elif x.endswith('ShapeOrig'):
                    mesh_orig = x

            if mesh is None or mesh_orig is None:
                cmds.warning(f'Mesh or mesh_orig is missing. Got -> mesh: {mesh!r}, mesh_orig: {mesh_orig!r}')
                continue

            create_multi_skin(mesh, mesh_orig, layers_number, setup_name)

        self.reload()

def open_multi_skin_editor():
    ui = MultiSkinEditor()
    ui.reload()
    ui.show()
    return ui