import sys
import threading
import os
import ctypes
from translations import TRANSLATIONS, LANGUAGES
import urllib.parse
import urllib.parse
import re
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QTabWidget, QLabel, QLineEdit, 
                             QPushButton, QComboBox, QMessageBox, QTreeWidget,
                             QTreeWidgetItem, QProgressBar, QListWidget, QListWidgetItem,
                             QInputDialog, QHeaderView, QFrame, QMenu, QDialog, QCompleter, QStyle, QToolButton, QTextEdit)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer
from PyQt6.QtGui import QIcon, QFont, QColor, QBrush, QDragEnterEvent, QDropEvent

from ssh_client import SSHClientWrapper
from database import Database

# --- QSS THEME ---
DARK_THEME = """
QMainWindow, QWidget {
    background-color: #2b2b2b;
    color: #ecf0f1;
    font-family: Arial;
    font-size: 13px;
}
QTabWidget::pane {
    border: 1px solid #34495e;
    background: #2b2b2b;
    border-radius: 5px;
}
QTabBar::tab {
    background: #34495e;
    color: white;
    padding: 10px 20px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QTabBar::tab:selected {
    background: #2980b9;
}
QPushButton {
    background-color: #2980b9;
    color: white;
    border: none;
    padding: 8px 16px;
    border-radius: 4px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #3498db;
}
QPushButton:disabled {
    background-color: #7f8c8d;
}
QPushButton:checked {
    background-color: #27ae60;
}
QLineEdit, QComboBox {
    background-color: #34495e;
    border: 1px solid #2c3e50;
    color: white;
    padding: 8px;
    border-radius: 4px;
}
QTreeWidget, QListWidget {
    background-color: #2c3e50;
    alternate-background-color: #34495e;
    border: 1px solid #1a252f;
    border-radius: 5px;
    outline: none;
}
QTreeWidget::item, QListWidget::item {
    padding: 5px;
}
QListWidget#queue_list::item {
    padding: 0px;
}
QTreeWidget::item:selected, QListWidget::item:selected {
    background-color: #2980b9;
}
QHeaderView::section {
    background-color: #2c3e50;
    color: white;
    padding: 6px;
    border: 1px solid #1a252f;
    font-weight: bold;
}
QProgressBar {
    border: 1px solid #34495e;
    border-radius: 4px;
    text-align: center;
    background: #2b2b2b;
    color: white;
    font-weight: bold;
}
QProgressBar::chunk {
    background-color: #27ae60;
    border-radius: 3px;
}
"""

class WorkerSignals(QObject):
    connected = pyqtSignal(bool, str, str, list)
    download_progress = pyqtSignal(object, object, object)
    download_done = pyqtSignal(bool, str)
    library_scanned = pyqtSignal(list)
    free_space_updated = pyqtSignal(str)

class ModelEditDialog(QDialog):
    def __init__(self, parent, data):
        super().__init__(parent)
        self.setWindowTitle(parent.tr("edit_model"))
        self.resize(500, 200)
        
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel(parent.tr("name_lbl")))
        self.name_entry = QLineEdit(data.get("name", data.get("filename", "")))
        layout.addWidget(self.name_entry)
        
        layout.addWidget(QLabel(parent.tr("new_url_lbl")))
        self.url_entry = QLineEdit(data.get("url", ""))
        layout.addWidget(self.url_entry)
        
        layout.addWidget(QLabel(parent.tr("folder_lbl")))
        self.folder_combo = QComboBox()
        self.folder_combo.setEditable(True)
        default_folders = sorted(["checkpoints", "loras", "vae", "clip", "clip_vision", "pulid", "upscale", "sams", "ultralytics", "controlnet", "unet", "annotators"])
        self.folder_combo.addItems(default_folders)
        self.folder_combo.setCurrentText(data.get("folder", ""))
        layout.addWidget(self.folder_combo)
        
        btn_layout = QHBoxLayout()
        save_btn = QPushButton(parent.tr("btn_save"))
        save_btn.setStyleSheet("background-color: #27ae60; color: white;")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton(parent.tr("btn_cancel"))
        cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)
        
    def get_data(self):
        return self.name_entry.text().strip(), self.url_entry.text().strip(), self.folder_combo.currentText().strip()

class PackageEditDialog(QDialog):
    def __init__(self, parent, db, original_name, group_items):
        super().__init__(parent)
        self.setWindowTitle(parent.tr("edit_pkg"))
        self.resize(600, 500)
        self.db = db
        
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel(parent.tr("pkg_name_lbl")))
        self.name_entry = QLineEdit(original_name)
        layout.addWidget(self.name_entry)
        
        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText(parent.tr("search_placeholder") if hasattr(parent, 'tr') else "Search...")
        self.search_entry.textChanged.connect(self.filter_tree)
        layout.addWidget(self.search_entry)
        
        layout.addWidget(QLabel(parent.tr("select_pkg_models")))
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Model"])
        layout.addWidget(self.tree)
        
        all_items = self.db.load_history()
        in_group = {(i.get('folder'), i.get('filename')) for i in group_items}
        scanned_map = { f"{item.get('folder')}/{item.get('filename')}" for item in parent.last_scanned_models_cache }
        
        grouped = {}
        for item in all_items:
            f = item.get('folder', 'unknown')
            if f not in grouped: grouped[f] = []
            grouped[f].append(item)
            
        for folder, items in grouped.items():
            f_root = QTreeWidgetItem(self.tree, [f"📁 {folder.upper()}"])
            f_root.setData(0, Qt.ItemDataRole.ForegroundRole, QColor("#3498db"))
            f_root.setExpanded(True)
            
            items.sort(key=lambda x: x.get('name', x.get('filename', '')).lower())
            
            for item in items:
                name = item.get('name', item.get('filename'))
                filename = item.get('filename')
                node = QTreeWidgetItem(f_root, [name])
                node.setFlags(node.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                
                if (folder, filename) in in_group:
                    node.setCheckState(0, Qt.CheckState.Checked)
                else:
                    node.setCheckState(0, Qt.CheckState.Unchecked)
                    
                if f"{folder}/{filename}" in scanned_map:
                    node.setForeground(0, QBrush(QColor("#2ecc71")))
                else:
                    node.setForeground(0, QBrush(QColor("#7f8c8d")))
                    
                node.setData(0, Qt.ItemDataRole.UserRole, item)
            
        btn_layout = QHBoxLayout()
        save_btn = QPushButton(parent.tr("btn_save"))
        save_btn.setStyleSheet("background-color: #27ae60; color: white;")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton(parent.tr("btn_cancel"))
        cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)
        
    def filter_tree(self, text):
        text = text.lower()
        for i in range(self.tree.topLevelItemCount()):
            folder_node = self.tree.topLevelItem(i)
            folder_visible = False
            for j in range(folder_node.childCount()):
                child = folder_node.child(j)
                name = child.text(0).lower()
                child_data = child.data(0, Qt.ItemDataRole.UserRole)
                filename = child_data.get('filename', '').lower() if child_data else ''
                if text in name or text in filename:
                    child.setHidden(False)
                    folder_visible = True
                else:
                    child.setHidden(True)
            folder_node.setHidden(not folder_visible)
        
    def get_updated_data(self):
        new_name = self.name_entry.text().strip()
        new_items = []
        for i in range(self.tree.topLevelItemCount()):
            folder_node = self.tree.topLevelItem(i)
            for j in range(folder_node.childCount()):
                child = folder_node.child(j)
                if child.checkState(0) == Qt.CheckState.Checked:
                    new_items.append(child.data(0, Qt.ItemDataRole.UserRole))
        return new_name, new_items

class QueueItemWidget(QWidget):
    def update_ui(self):
        is_paused = self.item_data.get("_paused", False)
        if self.is_active:
            status = self.parent_win.tr("status_downloading")
            color = "#2ecc71"
        elif is_paused:
            status = self.parent_win.tr("status_paused")
            color = "#f39c12"
        else:
            status = self.parent_win.tr("status_queue")
            color = "white"
        self.lbl.setText(f"<font color='{color}'><b>{status}</b></font> &nbsp;&nbsp; {self.item_data['filename']} &nbsp;➡️&nbsp; {self.item_data['folder']}")
        
        self.btn_pause.setText("►" if is_paused else "||")
        btn_color = "#2ecc71" if is_paused else "#f39c12"
        self.btn_pause.setStyleSheet(f"background-color: {btn_color}; color: white; font-size: 14px; font-weight: bold; border-radius: 4px; padding: 4px 8px;")

    def __init__(self, item_data, is_active, on_cancel, on_pause, parent=None):
        super().__init__(parent)
        self.parent_win = parent
        self.item_data = item_data
        self.is_active = is_active
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        self.setStyleSheet("background-color: transparent;")
        
        is_paused = item_data.get("_paused", False)
        if is_active:
            status = parent.tr("status_downloading")
            color = "#2ecc71"
        elif is_paused:
            status = parent.tr("status_paused")
            color = "#f39c12"
        else:
            status = parent.tr("status_queue")
            color = "white"
            
        self.lbl = QLabel(f"<font color='{color}'><b>{status}</b></font> &nbsp;&nbsp; {item_data['filename']} &nbsp;➡️&nbsp; {item_data['folder']}")
        self.lbl.setStyleSheet("background-color: transparent;")
        self.lbl.setContentsMargins(0, 0, 0, 2)
        layout.addWidget(self.lbl)
        
        layout.addStretch()
        
        self.btn_pause = QPushButton("►" if is_paused else "||")
        btn_color = "#2ecc71" if is_paused else "#f39c12"
        self.btn_pause.setStyleSheet(f"background-color: {btn_color}; color: white; font-size: 14px; font-weight: bold; border-radius: 4px; padding: 4px 8px;")
        self.btn_pause.clicked.connect(on_pause)
        layout.addWidget(self.btn_pause)
        
        self.btn_cancel = QPushButton("✕")
        self.btn_cancel.setStyleSheet("background-color: #e74c3c; color: white; font-size: 14px; font-weight: bold; border-radius: 4px; padding: 4px 8px;")
        self.btn_cancel.clicked.connect(on_cancel)
        layout.addWidget(self.btn_cancel)


class SSHModelManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SSH Model Manager")
        self.resize(1000, 700)
        self.setStyleSheet(DARK_THEME)
        self.setAcceptDrops(True)

        self.db = Database()
        self.config = self.db.load_config()
        self.ssh = SSHClientWrapper()
        
        self.signals = WorkerSignals()
        self.signals.connected.connect(self.on_connected_slot)
        self.signals.download_progress.connect(self.on_download_progress)
        self.signals.download_done.connect(self.on_download_done)
        self.signals.library_scanned.connect(self.on_library_scanned)
        self.signals.free_space_updated.connect(self.on_free_space_updated)

        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.timeout.connect(self.auto_refresh_tick)
        self.auto_refresh_timer.start(10000)
        
        self.download_queue = []
        self.current_download_item = None
        self.is_downloading = False
        self.queue_lock = threading.RLock()
        
        self.history_items = []
        self.last_scanned_models_cache = []
        
        self.lang = self.config.get("lang", "en")
        
        self.init_ui()


    def tr(self, key, *args):
        text = TRANSLATIONS.get(self.lang, TRANSLATIONS["en"]).get(key, TRANSLATIONS["en"].get(key, key))
        if args:
            return text.format(*args)
        return text

    def change_language(self, lang_name):
        self.lang = LANGUAGES.get(lang_name, "en")
        self.config["lang"] = self.lang
        self.db.save_config(self.config)
        self.retranslate_ui()

    def retranslate_ui(self):
        self.tabs.setTabText(0, self.tr("tab_conn"))
        self.tabs.setTabText(1, self.tr("tab_dl"))
        self.tabs.setTabText(2, self.tr("tab_lib"))
        self.tabs.setTabText(3, self.tr("tab_logs"))
        
        self.lbl_ssh_cmd.setText(self.tr("ssh_cmd_lbl"))
        self.ssh_cmd_entry.setPlaceholderText(self.tr("ssh_cmd_placeholder"))
        
        self.lbl_ip_entry.setText(self.tr("ip_host"))
        self.lbl_port_entry.setText(self.tr("port"))
        self.lbl_user_entry.setText(self.tr("user"))
        self.lbl_pass_entry.setText(self.tr("password"))
        self.lbl_key_entry.setText(self.tr("ssh_key"))
        self.lbl_key_pass_entry.setText(self.tr("key_pass"))
        self.lbl_hf_entry.setText(self.tr("hf_token"))
        self.lbl_civitai_entry.setText(self.tr("civitai_token"))
        
        if not self.ssh.connected:
            self.btn_connect.setText(self.tr("btn_connect"))
        else:
            self.btn_connect.setText(self.tr("connected"))
            
        self.btn_disconnect.setText(self.tr("btn_disconnect"))
        
        self.lbl_url.setText(self.tr("url_lbl"))
        self.url_entry.setPlaceholderText(self.tr("url_placeholder"))
        self.lbl_filename.setText(self.tr("filename_lbl"))
        self.lbl_folder.setText(self.tr("folder_lbl"))
        self.btn_add_queue.setText(self.tr("btn_add_queue"))
        self.lbl_queue_title.setText(self.tr("lbl_queue"))
        if not self.is_downloading:
            self.lbl_progress.setText(self.tr("lbl_waiting"))
        
        self.search_entry.setPlaceholderText(self.tr("search_placeholder"))
        self.btn_on_disk.setText(self.tr("btn_on_disk"))
        self.btn_refresh.setText(self.tr("btn_refresh"))
        if hasattr(self, 'btn_import_pkg'):
            self.btn_import_pkg.setText("📥 " + self.tr("btn_import_pkg"))
        
        self.tree.setHeaderLabels([self.tr("col_name"), self.tr("col_file"), self.tr("col_type"), self.tr("col_size")])
        self.btn_create_pkg.setText(self.tr("btn_create_pkg"))
        self.btn_mass_delete.setText(self.tr("btn_delete_selected"))
        self.btn_add_selected.setText(self.tr("btn_add_selected"))
        
        # Update queue items
        for i in range(self.queue_list.count()):
            item = self.queue_list.item(i)
            widget = self.queue_list.itemWidget(item)
            if widget:
                widget.update_ui()
                
        # Update status bar
        if self.ssh.connected:
            self.on_free_space_updated(self.last_space if hasattr(self, 'last_space') else "")
        else:
            self.status_bar.setText(self.tr("status_disconnected"))
            
        self.populate_library()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        
        self.tabs = QTabWidget()
        
        corner_widget = QWidget()
        corner_layout = QHBoxLayout(corner_widget)
        corner_layout.setContentsMargins(0, 0, 0, 0)
        
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["English", "Русский", "中文"])
        
        # Set initial combo text based on loaded self.lang
        lang_to_name = {v: k for k, v in LANGUAGES.items()}
        self.lang_combo.setCurrentText(lang_to_name.get(self.lang, "English"))
        
        self.lang_combo.currentTextChanged.connect(self.change_language)
        self.btn_help = QToolButton()
        self.btn_help.setText("?")
        self.btn_help.setFixedSize(24, 24)
        self.btn_help.setStyleSheet("""
            QToolButton {
                background-color: #2c3e50;
                color: white;
                border-radius: 12px;
                font-weight: bold;
                font-size: 14px;
                padding: 0px;
                margin: 0px;
            }
            QToolButton:hover {
                background-color: #34495e;
            }
        """)
        self.btn_help.clicked.connect(self.show_help)
        
        corner_layout.addWidget(self.lang_combo)
        corner_layout.addWidget(self.btn_help)
        
        self.tabs.setCornerWidget(corner_widget, Qt.Corner.TopRightCorner)
        
        main_layout.addWidget(self.tabs)
        
        self.tab_conn = QWidget()
        self.tab_dl = QWidget()
        self.tab_lib = QWidget()
        self.tab_logs = QWidget()
        
        self.tabs.addTab(self.tab_conn, self.tr("tab_conn"))
        self.tabs.addTab(self.tab_dl, self.tr("tab_dl"))
        self.tabs.addTab(self.tab_lib, self.tr("tab_lib"))
        self.tabs.addTab(self.tab_logs, self.tr("tab_logs"))
        
        self.status_bar = QLabel(self.tr("status_disconnected"))
        self.status_bar.setStyleSheet("color: #bdc3c7; padding: 5px;")
        main_layout.addWidget(self.status_bar)
        
        self.build_connection_tab()
        self.build_download_tab()
        self.build_library_tab()
        self.build_logs_tab()

    def load_logs_for_host(self, host):
        self.log_text.clear()
        if not host or not host.strip():
            host = "GLOBAL"
        logs_db = self.db.load_logs()
        for msg in logs_db.get(host, []):
            self.log_text.append(msg)
        
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def build_logs_tab(self):
        layout = QVBoxLayout(self.tab_logs)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; font-family: Consolas, monospace; font-size: 13px; padding: 5px;")
        layout.addWidget(self.log_text)
        
        host = self.config.get("ssh", {}).get("host", "GLOBAL")
        self.load_logs_for_host(host)

    def log_message(self, message, level="info"):
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        if level == "info":
            color, prefix = "#3498db", "[INFO]"
        elif level == "success":
            color, prefix = "#2ecc71", "[SUCCESS]"
        elif level == "error":
            color, prefix = "#e74c3c", "[ERROR]"
        elif level == "warning":
            color, prefix = "#f1c40f", "[WARNING]"
        else:
            color, prefix = "#d4d4d4", "[LOG]"
            
        html_msg = f'<span style="color: #7f8c8d;">[{timestamp}]</span> <span style="color: {color}; font-weight: bold;">{prefix}</span> <span style="color: #d4d4d4;">{message}</span>'
        self.log_text.append(html_msg)
        
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
        host = self.config.get("ssh", {}).get("host", "GLOBAL")
        if not host or not host.strip(): host = "GLOBAL"
        logs_db = self.db.load_logs()
        if host not in logs_db: logs_db[host] = []
        logs_db[host].append(html_msg)
        logs_db[host] = logs_db[host][-1000:]
        self.db.save_logs(logs_db)

    def build_connection_tab(self):
        layout = QVBoxLayout(self.tab_conn)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        layout.addSpacing(10)
        self.lbl_ssh_cmd = QLabel(self.tr("ssh_cmd_lbl"))
        layout.addWidget(self.lbl_ssh_cmd)
        self.ssh_cmd_entry = QLineEdit()
        self.ssh_cmd_entry.setPlaceholderText(self.tr("ssh_cmd_placeholder"))
        self.ssh_cmd_entry.textChanged.connect(self.parse_ssh_command)
        layout.addWidget(self.ssh_cmd_entry)
        
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #34495e; margin-top: 10px; margin-bottom: 10px;")
        layout.addWidget(sep)
        
        def add_row(label, var_name, default, placeholder="", password=False):
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setFixedWidth(150)
            setattr(self, "lbl_" + var_name, lbl)
            row.addWidget(lbl)
            entry = QLineEdit(str(default))
            entry.setPlaceholderText(placeholder)
            if password: entry.setEchoMode(QLineEdit.EchoMode.Password)
            row.addWidget(entry)
            layout.addLayout(row)
            setattr(self, var_name, entry)
            
        c = self.config["ssh"]
        layout.addSpacing(20)
        add_row(self.tr("ip_host"), "ip_entry", c.get("host", ""))
        add_row(self.tr("port"), "port_entry", c.get("port", "22"))
        add_row(self.tr("user"), "user_entry", c.get("username", "root"))
        add_row(self.tr("password"), "pass_entry", c.get("password", ""), password=True)
        add_row(self.tr("ssh_key"), "key_entry", c.get("key_filename", ""))
        add_row(self.tr("key_pass"), "key_pass_entry", c.get("key_passphrase", ""), password=True)
        
        layout.addSpacing(10)
        api_c = self.config.get("api", {})
        add_row(self.tr("hf_token"), "hf_entry", api_c.get("huggingface", ""))
        add_row(self.tr("civitai_token"), "civitai_entry", api_c.get("civitai", ""))
        self.hf_entry.textChanged.connect(self.on_api_keys_changed)
        self.civitai_entry.textChanged.connect(self.on_api_keys_changed)
        layout.addSpacing(20)
        
        bot = QHBoxLayout()
        self.btn_connect = QPushButton(self.tr("btn_connect"))
        self.btn_connect.clicked.connect(self.do_connect)
        bot.addWidget(self.btn_connect)
        
        self.btn_disconnect = QPushButton(self.tr("btn_disconnect"))
        self.btn_disconnect.setStyleSheet("QPushButton:enabled { background-color: #e74c3c; }")
        self.btn_disconnect.setEnabled(False)
        self.btn_disconnect.clicked.connect(self.do_disconnect)
        bot.addWidget(self.btn_disconnect)
        
        layout.addLayout(bot)

    def parse_ssh_command(self, text):
        cmd = text.strip()
        if not cmd.startswith("ssh "):
            return
            
        port_match = re.search(r"-p\s+(\d+)", cmd)
        if port_match:
            self.port_entry.setText(port_match.group(1))
        else:
            self.port_entry.setText("22")
            
        user_host_match = re.search(r"([a-zA-Z0-9_-]+)@([a-zA-Z0-9.-]+)", cmd)
        if user_host_match:
            self.user_entry.setText(user_host_match.group(1))
            self.ip_entry.setText(user_host_match.group(2))

    def do_connect(self):
        self.btn_connect.setEnabled(False)
        self.btn_connect.setText(self.tr("connecting"))
        
        self.config["ssh"]["host"] = self.ip_entry.text()
        try: self.config["ssh"]["port"] = int(self.port_entry.text())
        except: self.config["ssh"]["port"] = 22
        self.config["ssh"]["username"] = self.user_entry.text()
        self.config["ssh"]["password"] = self.pass_entry.text()
        self.config["ssh"]["key_filename"] = self.key_entry.text()
        self.config["ssh"]["key_passphrase"] = self.key_pass_entry.text()
        
        if "api" not in self.config: self.config["api"] = {}
        self.config["api"]["huggingface"] = self.hf_entry.text()
        self.config["api"]["civitai"] = self.civitai_entry.text()
        
        self.db.save_config(self.config)
        
        def t():
            success, msg = self.ssh.connect(
                self.config["ssh"]["host"], self.config["ssh"]["port"],
                self.config["ssh"]["username"], self.config["ssh"]["password"],
                self.config["ssh"]["key_filename"], self.config["ssh"]["key_passphrase"]
            )
            if success:
                self.ssh.find_comfy_root()
                space = self.ssh.get_disk_space()
                folders = self.ssh.list_model_folders()
                self.signals.connected.emit(True, "", space, folders)
            else:
                self.signals.connected.emit(False, msg, "", [])
        threading.Thread(target=t, daemon=True).start()

    def on_api_keys_changed(self):
        if "api" not in self.config:
            self.config["api"] = {}
        self.config["api"]["huggingface"] = self.hf_entry.text().strip()
        self.config["api"]["civitai"] = self.civitai_entry.text().strip()
        self.db.save_config(self.config)

    def on_connected_slot(self, success, msg, space, folders):
        if success:
            host = self.config.get("ssh", {}).get("host", "GLOBAL")
            self.load_logs_for_host(host)
            
            self.btn_connect.setText(self.tr("connected"))
            self.btn_connect.setStyleSheet("background-color: #27ae60;")
            self.btn_disconnect.setEnabled(True)
            self.on_free_space_updated(space)
            if folders:
                current_text = self.folder_combo.currentText()
                self.folder_combo.clear()
                self.folder_combo.addItems(sorted(folders))
                self.folder_combo.setCurrentText(current_text)
            self.populate_library()
        else:
            QMessageBox.critical(self, self.tr("err"), msg)
            self.btn_connect.setEnabled(True)
            self.btn_connect.setText(self.tr("btn_connect"))
            self.btn_connect.setStyleSheet("")

    def on_free_space_updated(self, space):
        self.last_space = space
        self.status_bar.setText(self.tr("status_connected", self.ssh.comfy_root, space))

    def auto_refresh_tick(self):
        if self.ssh.connected:
            self.refresh_library_thread()

    def do_disconnect(self):
        self.ssh.disconnect()
        self.btn_connect.setEnabled(True)
        self.btn_connect.setText(self.tr("btn_connect"))
        self.btn_connect.setStyleSheet("")
        self.btn_disconnect.setEnabled(False)
        self.status_bar.setText(self.tr("status_disconnected"))



    def build_download_tab(self):
        layout = QVBoxLayout(self.tab_dl)
        
        row1 = QHBoxLayout()
        self.lbl_url = QLabel(self.tr("url_lbl"))
        row1.addWidget(self.lbl_url)
        self.url_entry = QLineEdit()
        self.url_entry.setPlaceholderText(self.tr("url_placeholder"))
        self.url_entry.textChanged.connect(self.auto_extract_filename)
        row1.addWidget(self.url_entry)
        layout.addLayout(row1)
        
        row2 = QHBoxLayout()
        self.lbl_filename = QLabel(self.tr("filename_lbl"))
        row2.addWidget(self.lbl_filename)
        self.filename_entry = QLineEdit()
        row2.addWidget(self.filename_entry)
        self.lbl_folder = QLabel(self.tr("folder_lbl"))
        row2.addWidget(self.lbl_folder)
        self.folder_combo = QComboBox()
        self.folder_combo.setMinimumWidth(250)
        self.folder_combo.setEditable(True)
        font = QFont()
        font.setPointSize(11)
        self.folder_combo.setFont(font)
        self.folder_combo.view().setFont(font)
        self.folder_combo.setStyleSheet("QComboBox QAbstractItemView { min-width: 350px; padding: 4px; }")
        
        self.folder_combo.completer().setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.folder_combo.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.folder_combo.currentTextChanged.connect(self.on_folder_changed)
        
        default_folders = sorted(["checkpoints", "loras", "vae", "clip", "clip_vision", "pulid", "upscale", "sams", "ultralytics", "controlnet", "unet", "annotators"])
        self.folder_combo.addItems(default_folders)
        self.folder_combo.setCurrentText("")
        
        row2.addWidget(self.folder_combo)
        layout.addLayout(row2)
        
        self.btn_add_queue = QPushButton(self.tr("btn_add_queue"))
        self.btn_add_queue.clicked.connect(self.add_to_queue)
        layout.addWidget(self.btn_add_queue)
        
        row_prog = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        row_prog.addWidget(self.progress_bar)
        
        self.btn_pause_active = QPushButton("||")
        self.btn_pause_active.setStyleSheet("background-color: #f39c12; color: white; font-weight: bold; padding: 4px 10px; border-radius: 3px;")
        self.btn_pause_active.clicked.connect(self.toggle_global_pause)
        self.btn_pause_active.hide()
        row_prog.addWidget(self.btn_pause_active)
        layout.addLayout(row_prog)
        
        self.lbl_progress = QLabel(self.tr("lbl_waiting"))
        self.lbl_progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_progress)
        
        self.lbl_queue_title = QLabel(self.tr("lbl_queue"))
        layout.addWidget(self.lbl_queue_title)
        self.queue_list = QListWidget()
        self.queue_list.setObjectName("queue_list")
        self.queue_list.setAlternatingRowColors(True)
        layout.addWidget(self.queue_list)

    def auto_extract_filename(self, text):
        if not text: return
        try:
            if "huggingface.co" in text and "/blob/" in text:
                text = text.replace("/blob/", "/resolve/")
                if not text.endswith("?download=true"):
                    text += "?download=true"
                self.url_entry.blockSignals(True)
                self.url_entry.setText(text)
                self.url_entry.blockSignals(False)
                
            path_parts = urllib.parse.urlparse(text).path.split('/')
            
            # Вставляем имя файла
            if "api" not in text:
                filename = path_parts[-1]
                if "." in filename:
                    self.filename_entry.setText(filename)
                    
            # Пытаемся угадать папку
            combo_items = {self.folder_combo.itemText(i) for i in range(self.folder_combo.count())}
            known_folders = {"checkpoints", "loras", "vae", "clip", "clip_vision", "pulid", "upscale", "sams", "ultralytics", "controlnet", "unet", "annotators", "text_encoders", "audio_encoders", "style_models", "photomaker", "gligen", "hypernetworks", "embeddings", "diffusion_models"}
            all_valid = combo_items.union(known_folders)
            
            synonyms = {"upscale_models": "upscale"}
            
            found_folder = False
            for part in reversed(path_parts):
                part_lower = part.lower()
                part_lower = synonyms.get(part_lower, part_lower)
                if part_lower in all_valid:
                    self.folder_combo.setCurrentText(part_lower)
                    found_folder = True
                    break
                    
            if not found_folder:
                self.folder_combo.setCurrentText("")
                self.folder_combo.setStyleSheet("QComboBox { border: 2px solid #e74c3c; } QComboBox QAbstractItemView { min-width: 350px; padding: 4px; }")
                
        except: pass
        
    def on_folder_changed(self, text):
        self.folder_combo.setStyleSheet("QComboBox QAbstractItemView { min-width: 350px; padding: 4px; }")

    def add_to_queue(self):
        url = self.url_entry.text().strip()
        filename = self.filename_entry.text().strip()
        folder = self.folder_combo.currentText().strip()
        if not url or not filename or not folder:
            if not folder:
                self.folder_combo.setStyleSheet("QComboBox { border: 2px solid #e74c3c; } QComboBox QAbstractItemView { min-width: 350px; padding: 4px; }")
            QMessageBox.warning(self, self.tr("err"), self.tr("err_req_fields"))
            return
        if not self.ssh.connected:
            QMessageBox.warning(self, self.tr("err"), self.tr("err_no_ssh"))
            return
            
        with self.queue_lock:
            self.download_queue.append({"url": url, "filename": filename, "folder": folder})
            
        self.url_entry.clear()
        self.filename_entry.clear()
        self.db.add_history_item({"name": filename, "url": url, "filename": filename, "folder": folder})
        self.populate_library()
        self.refresh_queue_ui()
        self.process_queue()

    def refresh_queue_ui(self):
        self.queue_list.clear()
        with self.queue_lock:
            if self.is_downloading and self.current_download_item:
                self.add_queue_row(self.current_download_item, is_active=True)
            for item in self.download_queue:
                self.add_queue_row(item, is_active=False)
        self.update_global_pause_btn()

    def update_global_pause_btn(self):
        with self.queue_lock:
            total_items = len(self.download_queue) + (1 if self.is_downloading else 0)
            if total_items == 0:
                self.btn_pause_active.hide()
                return
                
            any_active = self.is_downloading
            if not any_active:
                for item in self.download_queue:
                    if not item.get("_paused", False):
                        any_active = True
                        break
                        
            self.btn_pause_active.show()
            if any_active:
                self.btn_pause_active.setText("||")
                self.btn_pause_active.setStyleSheet("background-color: #f39c12; color: white; font-weight: bold; padding: 4px 10px; border-radius: 3px;")
            else:
                self.btn_pause_active.setText("►")
                self.btn_pause_active.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold; padding: 4px 10px; border-radius: 3px;")

    def add_queue_row(self, item, is_active):
        def on_cancel():
            if is_active:
                item["_cancelled"] = True
                self.ssh.cancel_download()
            else:
                with self.queue_lock:
                    if item in self.download_queue: self.download_queue.remove(item)
                self.refresh_queue_ui()
                
        def on_pause():
            if is_active:
                self.ssh.cancel_download()
                with self.queue_lock:
                    item["_paused"] = True
                    self.download_queue.insert(0, item)
            else:
                with self.queue_lock:
                    item["_paused"] = not item.get("_paused", False)
            self.refresh_queue_ui()
            if not is_active and not item.get("_paused", False):
                self.process_queue()
                
        list_item = QListWidgetItem(self.queue_list)
        widget = QueueItemWidget(item, is_active, on_cancel, on_pause, parent=self)
        list_item.setSizeHint(widget.sizeHint())
        self.queue_list.setItemWidget(list_item, widget)

    def process_queue(self):
        with self.queue_lock:
            next_idx = -1
            for i, item in enumerate(self.download_queue):
                if not item.get("_paused", False):
                    next_idx = i
                    break
            if self.is_downloading or next_idx == -1:
                if next_idx == -1 and not self.is_downloading:
                    self.lbl_progress.setText(self.tr("lbl_waiting"))
                    self.progress_bar.setValue(0)
                    self.current_download_item = None
                    self.refresh_queue_ui()
                return
            self.current_download_item = self.download_queue.pop(next_idx)
            self.is_downloading = True
            
        self.refresh_queue_ui()
        threading.Thread(target=self.start_download, args=(self.current_download_item,), daemon=True).start()

    def format_bytes(self, b):
        return f"{b / (1024*1024):.2f} MB" if b < 1024*1024*1024 else f"{b / (1024*1024*1024):.2f} GB"

    def start_download(self, item):
        url = item['url']
        filename = item['filename']
        folder = item['folder']
        
        token = ""
        if "civitai.com" in url:
            civitai_token = self.config["api"].get("civitai", "")
            if civitai_token:
                import urllib.parse
                parsed = urllib.parse.urlparse(url)
                query = urllib.parse.parse_qs(parsed.query)
                query['token'] = [civitai_token]
                new_query = urllib.parse.urlencode(query, doseq=True)
                url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
        elif "huggingface.co" in url:
            token = self.config["api"].get("huggingface", "")
            
        def p_cb(dl, tot, sp):
            self.signals.download_progress.emit(dl, tot, sp)
        def c_cb(success, msg):
            self.signals.download_done.emit(success, msg)
            
        if url.startswith("local://"):
            local_path = url[len("local://"):]
            self.ssh.upload_file(local_path, folder, filename, p_cb, c_cb)
        else:
            self.ssh.download_file(url, folder, filename, token, p_cb, c_cb)

    def on_download_progress(self, dl, tot, speed):
        if tot > 0:
            percent = int((dl / tot) * 100)
            self.progress_bar.setValue(percent)
            
            eta_str = ""
            if speed > 0:
                eta_sec = (tot - dl) / speed
                if eta_sec > 0:
                    m, s = divmod(int(eta_sec), 60)
                    h, m = divmod(m, 60)
                    if h > 0:
                        eta_str = self.tr("eta_hm", h, m)
                    else:
                        eta_str = self.tr("eta_ms", m, s)
            
            self.lbl_progress.setText(f"{self.format_bytes(dl)} / {self.format_bytes(tot)} ({self.format_bytes(speed)}/s){eta_str}")

    def on_download_done(self, success, msg):
        item = self.current_download_item
        self.is_downloading = False
        self.current_download_item = None
        
        if not success and item:
            # Delete remote file if direct download failed, or if SFTP upload was explicitly cancelled
            if not item['url'].startswith('local://') or item.get("_cancelled"):
                self.ssh.delete_file(item['folder'], item['filename'])
                    
        if item:
            filename = item.get('filename', 'Unknown')
            if success and msg == "AlreadyExists":
                self.log_message(f"{filename} - {self.tr('file_exists_msg')}", "info")
            elif success:
                self.log_message(f"{filename} - {self.tr('log_dl_success')}", "success")
            elif not success and msg != "Connection closed unexpectedly" and msg != "Upload paused" and not item.get("_cancelled"):
                self.log_message(f"{filename} - {self.tr('log_dl_error', str(msg))}", "error")
                
            # If download/upload failed (not cancelled) and inputs are empty, restore details for editing
            if not success and not item.get("_cancelled") and msg != "Upload paused":
                if not self.url_entry.text().strip():
                    self.url_entry.setText(item.get("url", ""))
                    self.filename_entry.setText(item.get("filename", ""))
                    idx = self.folder_combo.findText(item.get("folder", ""))
                    if idx >= 0:
                        self.folder_combo.setCurrentIndex(idx)
                        
        self.process_queue()
        self.populate_library()

    def build_library_tab(self):
        layout = QVBoxLayout(self.tab_lib)
        
        top = QHBoxLayout()
        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText(self.tr("search_placeholder"))
        self.search_entry.textChanged.connect(lambda: self.populate_library(self.last_scanned_models_cache))
        top.addWidget(self.search_entry)
        
        self.btn_on_disk = QPushButton(self.tr("btn_on_disk"))
        self.btn_on_disk.setCheckable(True)
        self.btn_on_disk.clicked.connect(lambda: self.populate_library(self.last_scanned_models_cache))
        top.addWidget(self.btn_on_disk)
        
        self.btn_refresh = QPushButton(self.tr("btn_refresh"))
        self.btn_refresh.clicked.connect(self.refresh_library_thread)
        top.addWidget(self.btn_refresh)
        
        self.btn_import_pkg = QPushButton("📥 " + self.tr("btn_import_pkg"))
        self.btn_import_pkg.clicked.connect(self.import_package_dialog)
        top.addWidget(self.btn_import_pkg)
        
        layout.addLayout(top)
        
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([self.tr("col_name"), self.tr("col_file"), self.tr("col_type"), self.tr("col_size")])
        self.tree.setColumnWidth(0, 400)
        self.tree.setColumnWidth(1, 300)
        self.tree.setColumnWidth(2, 100)
        self.tree.setAlternatingRowColors(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)
        self.tree.itemChanged.connect(self.on_tree_item_changed)
        layout.addWidget(self.tree)
        
        bot = QHBoxLayout()
        self.btn_add_selected = QPushButton(self.tr("btn_add_selected"))
        self.btn_add_selected.clicked.connect(self.do_mass_queue)
        bot.addWidget(self.btn_add_selected)
        
        self.btn_create_pkg = QPushButton(self.tr("btn_create_pkg"))
        self.btn_create_pkg.setStyleSheet("background-color: #8e44ad;")
        self.btn_create_pkg.hide()
        self.btn_create_pkg.clicked.connect(self.create_group)
        bot.addWidget(self.btn_create_pkg)
        
        self.btn_mass_delete = QPushButton(self.tr("btn_delete_selected"))
        self.btn_mass_delete.setStyleSheet("background-color: #c0392b;")
        self.btn_mass_delete.hide()
        self.btn_mass_delete.clicked.connect(self.do_mass_delete)
        bot.addWidget(self.btn_mass_delete)
        
        layout.addLayout(bot)
        
        self.populate_library()

    def show_context_menu(self, position):
        item = self.tree.itemAt(position)
        if not item: return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data: return
        
        menu = QMenu()
        menu.setStyleSheet("QMenu { background-color: #34495e; color: white; border: 1px solid #2c3e50; } QMenu::item:selected { background-color: #2980b9; }")
        
        if data.get("_is_group"):
            group_name = data.get("name")
            edit_pkg_action = menu.addAction(self.tr("ctx_edit_pkg"))
            export_pkg_action = menu.addAction(self.tr("ctx_export_pkg"))
            del_pkg_lib_action = menu.addAction(self.tr("ctx_del_pkg_lib"))
            del_files_srv_action = None
            del_pkg_and_files_srv_action = None
            if self.ssh.connected:
                menu.addSeparator()
                del_files_srv_action = menu.addAction(self.tr("ctx_del_files_srv"))
                del_pkg_and_files_srv_action = menu.addAction(self.tr("ctx_del_pkg_and_files_srv"))
                
            action = menu.exec(self.tree.viewport().mapToGlobal(position))
            if action == edit_pkg_action:
                groups = self.db.load_groups()
                group_items = groups.get(group_name, [])
                dialog = PackageEditDialog(self, self.db, group_name, group_items)
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    new_name, new_items = dialog.get_updated_data()
                    if new_name:
                        del groups[group_name]
                        groups[new_name] = new_items
                        self.db.save_groups(groups)
                        self.populate_library()
            elif action == export_pkg_action:
                self.export_package(group_name)
            elif action == del_pkg_lib_action:
                reply = QMessageBox.question(self, self.tr("warn"), self.tr("del_pkg_confirm").format(group_name), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if reply == QMessageBox.StandardButton.Yes:
                    groups = self.db.load_groups()
                    if group_name in groups:
                        del groups[group_name]
                        self.db.save_groups(groups)
                        self.populate_library()
            elif del_files_srv_action and action == del_files_srv_action:
                reply = QMessageBox.question(self, self.tr("warn"), self.tr("del_pkg_srv_confirm").format(group_name), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if reply == QMessageBox.StandardButton.Yes:
                    groups = self.db.load_groups()
                    if group_name in groups:
                        items_to_del = groups[group_name]
                        errors = []
                        for it in items_to_del:
                            succ, err = self.ssh.delete_file(it["folder"], it["filename"])
                            if not succ:
                                errors.append(f"{it['filename']}: {err}")
                        
                        if errors:
                            QMessageBox.warning(self, self.tr("del_err_title"), self.tr("del_err_msg").format("\n".join(errors)))
                        else:
                            QMessageBox.information(self, self.tr("success"), self.tr("del_pkg_success"))
                        self.refresh_library_thread()
            elif del_pkg_and_files_srv_action and action == del_pkg_and_files_srv_action:
                reply = QMessageBox.question(self, self.tr("warn"), self.tr("del_pkg_srv_confirm").format(group_name), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if reply == QMessageBox.StandardButton.Yes:
                    groups = self.db.load_groups()
                    if group_name in groups:
                        items_to_del = groups[group_name]
                        errors = []
                        for it in items_to_del:
                            succ, err = self.ssh.delete_file(it["folder"], it["filename"])
                            if not succ:
                                errors.append(f"{it['filename']}: {err}")
                        
                        if errors:
                            QMessageBox.warning(self, self.tr("del_err_title"), self.tr("del_err_msg").format("\n".join(errors)))
                        else:
                            del groups[group_name]
                            self.db.save_groups(groups)
                            QMessageBox.information(self, self.tr("success"), self.tr("del_pkg_success"))
                        self.refresh_library_thread()
            return
            
        edit_action = menu.addAction(self.tr("ctx_edit"))
        delete_lib_action = menu.addAction(self.tr("ctx_del_lib"))
        
        delete_server_action = None
        if data.get("_exists", True) and self.ssh.connected:
            menu.addSeparator()
            delete_server_action = menu.addAction(self.tr("ctx_del_server"))
        
        action = menu.exec(self.tree.viewport().mapToGlobal(position))
        
        if action == edit_action:
            dialog = ModelEditDialog(self, data)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                new_name, new_url, new_folder = dialog.get_data()
                
                old_folder = data.get("folder")
                filename = data.get("filename")
                
                if new_folder != old_folder:
                    if self.ssh.connected and data.get("_exists", True):
                        succ, msg = self.ssh.move_file(old_folder, filename, new_folder, filename)
                        if not succ:
                            QMessageBox.critical(self, self.tr("err"), self.tr("move_err_msg").format(msg))
                            return
                            
                    self.db.update_history_model_data(old_folder, filename, new_name, new_folder, new_url)
                    
                    groups = self.db.load_groups()
                    modified_groups = False
                    for g_name, g_items in groups.items():
                        for item in g_items:
                            if item.get("folder") == old_folder and item.get("filename") == filename:
                                item["folder"] = new_folder
                                item["name"] = new_name
                                modified_groups = True
                    if modified_groups:
                        self.db.save_groups(groups)
                else:
                    self.db.update_history_model_data(old_folder, filename, new_name, old_folder, new_url)
                    
                data["name"] = new_name
                data["url"] = new_url
                data["folder"] = new_folder
                
                if self.ssh.connected:
                    self.refresh_library_thread()
                else:
                    self.populate_library()
        elif action == delete_lib_action:
            reply = QMessageBox.question(self, self.tr("warn"), self.tr("del_lib_confirm", data["name"]), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.db.delete_history_item(data["folder"], data["filename"])
                self.populate_library()
        elif delete_server_action and action == delete_server_action:
            reply = QMessageBox.question(self, self.tr("warn"), self.tr("del_server_confirm", data["filename"]), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                success, msg = self.ssh.delete_file(data["folder"], data["filename"])
                if success:
                    QMessageBox.information(self, self.tr("success"), self.tr("del_file_success"))
                    self.refresh_library_thread()
                else:
                    QMessageBox.critical(self, self.tr("err"), self.tr("del_file_err").format(msg))

    def refresh_library_thread(self):
        if self.ssh.connected:
            def t():
                sc = self.ssh.scan_models()
                df_success, df_out = self.ssh.execute_command(f"df -h {self.ssh.comfy_root} | tail -n 1 | awk '{{print $4}}'")
                if df_success:
                    self.signals.free_space_updated.emit(df_out.strip())
                self.signals.library_scanned.emit(sc)
            threading.Thread(target=t, daemon=True).start()
        else:
            self.populate_library()
            
    def on_library_scanned(self, scanned):
        self.populate_library(scanned)

    def populate_library(self, scanned_models=None):
        expanded_state = {}
        checked_state = set()
        
        if hasattr(self, 'history_items'):
            for node in self.history_items:
                if node.checkState(0) == Qt.CheckState.Checked:
                    data = node.data(0, Qt.ItemDataRole.UserRole)
                    if data:
                        if data.get("_is_group"):
                            checked_state.add(f"group:{data.get('name')}")
                        else:
                            checked_state.add(f"item:{data.get('folder')}/{data.get('filename')}")
                            
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            expanded_state[item.text(0)] = item.isExpanded()
            
        self.tree.blockSignals(True)
        self.tree.clear()
        self.history_items = []
        
        history = self.db.load_history()
        history_map = { f"{item.get('folder')}/{item.get('filename')}" : item for item in history }
        
        if scanned_models is None or isinstance(scanned_models, bool):
            scanned_models = self.last_scanned_models_cache
                
        self.last_scanned_models_cache = scanned_models
        scanned_map = { f"{item.get('folder')}/{item.get('filename')}" : item for item in scanned_models }
        
        all_keys = set(history_map.keys()).union(scanned_map.keys())
        merged = []
        for k in all_keys:
            if k in history_map:
                item = history_map[k]
                item['_tracked'] = True
                item['_exists'] = k in scanned_map
                if item['_exists']:
                    item['size'] = scanned_map[k].get('size', '')
                    item['size_bytes'] = scanned_map[k].get('size_bytes', 0)
            else:
                item = scanned_map[k]
                item['name'] = item['filename']
                item['url'] = ""
                item['_tracked'] = False
                item['_exists'] = True
            merged.append(item)
            
        sq = self.search_entry.text().lower().strip()
        if sq:
            merged = [i for i in merged if sq in i['name'].lower() or sq in i['filename'].lower()]
            
        if hasattr(self, 'btn_on_disk') and self.btn_on_disk.isChecked():
            merged = [i for i in merged if i.get('_exists', False)]
            
        groups = self.db.load_groups()
        if groups and not sq:
            grp_root = QTreeWidgetItem(self.tree, [self.tr("pkg_root"), "", "", ""])
            grp_root.setForeground(0, QBrush(QColor("#3498db")))
            grp_root.setExpanded(True)
            
            for g_name, g_items in groups.items():
                # Подсчитываем, сколько моделей из пакета реально есть на диске
                exists_count = sum(1 for it in g_items if f"{it.get('folder')}/{it.get('filename')}" in scanned_map)
                
                if hasattr(self, 'btn_on_disk') and self.btn_on_disk.isChecked() and exists_count == 0:
                    continue
                    
                total_bytes = sum(scanned_map[f"{it.get('folder')}/{it.get('filename')}"].get('size_bytes', 0) for it in g_items if f"{it.get('folder')}/{it.get('filename')}" in scanned_map)
                size_str = self.format_bytes(total_bytes) if total_bytes > 0 else ""
                
                node = QTreeWidgetItem(grp_root, [g_name, f"{len(g_items)} models", "Package", size_str])
                node.setFlags(node.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                if f"group:{g_name}" in checked_state:
                    node.setCheckState(0, Qt.CheckState.Checked)
                else:
                    node.setCheckState(0, Qt.CheckState.Unchecked)
                node.setData(0, Qt.ItemDataRole.UserRole, {"_is_group": True, "name": g_name, "items": g_items})
                
                if exists_count == 0:
                    color = QColor("#7f8c8d") # Серый (нет ни одной)
                elif exists_count == len(g_items):
                    color = QColor("#2ecc71") # Зеленый (все на диске)
                else:
                    color = QColor("#f39c12") # Оранжевый (частично)
                    
                node.setForeground(0, QBrush(color))
                node.setForeground(1, QBrush(color))
                node.setForeground(2, QBrush(color))
                node.setForeground(3, QBrush(color))
                
                self.history_items.append(node)
                
            if grp_root.childCount() == 0:
                self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(grp_root))
                
        grouped = {}
        for item in merged:
            f = item.get('folder', 'unknown')
            if f not in grouped: grouped[f] = []
            grouped[f].append(item)
            
        for folder, items in grouped.items():
            f_root = QTreeWidgetItem(self.tree, [f"📁 {folder.upper()}", "", "", ""])
            f_root.setData(0, Qt.ItemDataRole.ForegroundRole, "#3498db")
            f_root.setExpanded(True)
            items.sort(key=lambda x: (not x['_tracked'], x['name'].lower()))
            
            for item in items:
                node = QTreeWidgetItem(f_root, [item['name'], item['filename'], folder, item.get('size', '')])
                node.setFlags(node.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                if f"item:{item.get('folder')}/{item.get('filename')}" in checked_state:
                    node.setCheckState(0, Qt.CheckState.Checked)
                else:
                    node.setCheckState(0, Qt.CheckState.Unchecked)
                node.setData(0, Qt.ItemDataRole.UserRole, item)
                
                if not item.get('_exists', True):
                    # Отсутствует на сервере -> серый цвет
                    node.setForeground(0, QBrush(QColor("#7f8c8d")))
                    node.setForeground(1, QBrush(QColor("#7f8c8d")))
                    node.setForeground(2, QBrush(QColor("#7f8c8d")))
                else:
                    # Присутствует на сервере -> выделяем зеленым
                    node.setForeground(0, QBrush(QColor("#2ecc71")))
                    node.setForeground(1, QBrush(QColor("#2ecc71")))
                    node.setForeground(2, QBrush(QColor("#2ecc71")))
                
                self.history_items.append(node)
                
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.text(0) in expanded_state:
                item.setExpanded(expanded_state[item.text(0)])
                
        self.tree.blockSignals(False)
        self.on_tree_item_changed()

    def on_tree_item_changed(self):
        selected = 0
        for node in self.history_items:
            if node.checkState(0) == Qt.CheckState.Checked:
                data = node.data(0, Qt.ItemDataRole.UserRole)
                if not data.get("_is_group"):
                    selected += 1
        self.btn_create_pkg.setVisible(selected >= 2)
        self.btn_mass_delete.setVisible(selected >= 2)

    def do_mass_delete(self):
        items_to_del = []
        for node in self.history_items:
            if node.checkState(0) == Qt.CheckState.Checked:
                data = node.data(0, Qt.ItemDataRole.UserRole)
                if not data.get("_is_group") and data.get("_exists", False):
                    items_to_del.append(data)
                    
        if not items_to_del: return
        
        reply = QMessageBox.question(self, self.tr("warn"), self.tr("mass_del_confirm", len(items_to_del)), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            errors = []
            for it in items_to_del:
                succ, msg = self.ssh.delete_file(it["folder"], it["filename"])
                if not succ:
                    errors.append(f"{it['filename']}: {msg}")
            
            if errors:
                QMessageBox.critical(self, self.tr("del_files_err_title"), "\n".join(errors))
            else:
                QMessageBox.information(self, self.tr("success"), self.tr("del_files_success"))
                
            self.refresh_library_thread()

    def create_group(self):
        items_to_add = []
        for node in self.history_items:
            if node.checkState(0) == Qt.CheckState.Checked:
                data = node.data(0, Qt.ItemDataRole.UserRole)
                if not data.get("_is_group"):
                    items_to_add.append(data)
                    
        if len(items_to_add) < 2: return
        
        dialog = QInputDialog(self)
        dialog.setWindowTitle(self.tr("create_pkg"))
        dialog.setLabelText(self.tr("create_pkg_name"))
        dialog.setTextEchoMode(QLineEdit.EchoMode.Normal)
        dialog.resize(500, 150)
        
        if dialog.exec() == QInputDialog.DialogCode.Accepted:
            name = dialog.textValue().strip()
            if name:
                groups = self.db.load_groups()
                if name not in groups:
                    for item in items_to_add:
                        if not item.get("_tracked", True):
                            import uuid
                            item_copy = dict(item)
                            item_copy["id"] = str(uuid.uuid4())
                            item_copy["url"] = ""
                            item_copy.pop("_exists", None)
                            item_copy.pop("_tracked", None)
                            self.db.add_history_item(item_copy)
                    groups[name] = items_to_add
                    self.db.save_groups(groups)
                    self.populate_library()

    def toggle_global_pause(self):
        with self.queue_lock:
            any_active = self.is_downloading
            if not any_active:
                for item in self.download_queue:
                    if not item.get("_paused", False):
                        any_active = True
                        break
                        
            if any_active:
                if self.is_downloading and self.current_download_item:
                    self.ssh.cancel_download()
                    self.current_download_item["_paused"] = True
                    self.download_queue.insert(0, self.current_download_item)
                for item in self.download_queue:
                    item["_paused"] = True
            else:
                for item in self.download_queue:
                    item["_paused"] = False

        self.refresh_queue_ui()
        self.process_queue()

    def pause_active_download(self):
        if self.current_download_item:
            self.ssh.cancel_download()
            self.current_download_item["_paused"] = True
            with self.queue_lock:
                self.download_queue.insert(0, self.current_download_item)
            self.refresh_queue_ui()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if os.path.isfile(file_path):
                if file_path.endswith('.json'):
                    self.import_package_from_file(file_path)
                    return
                
                self.tabs.setCurrentIndex(1)
                self.url_entry.blockSignals(True)
                self.url_entry.setText(f"local://{file_path}")
                self.url_entry.blockSignals(False)
                
                filename = os.path.basename(file_path)
                self.filename_entry.setText(filename)
                
                parent_dir = os.path.basename(os.path.dirname(file_path)).lower()
                combo_items = {self.folder_combo.itemText(i).lower() for i in range(self.folder_combo.count())}
                if parent_dir in combo_items:
                    self.folder_combo.setCurrentText(parent_dir)
                else:
                    synonyms = {"upscale_models": "upscale", "embeddings": "embeddings", "hypernetworks": "hypernetworks"}
                    parent_dir = synonyms.get(parent_dir, parent_dir)
                    if parent_dir in combo_items:
                        self.folder_combo.setCurrentText(parent_dir)
                    else:
                        self.folder_combo.setCurrentText("")

    def import_package_dialog(self):
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, self.tr("btn_import_pkg"), "", "JSON Files (*.json)")
        if path:
            self.import_package_from_file(path)

    def import_package_from_file(self, filepath):
        import json
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            if "group_name" not in data or "items" not in data:
                QMessageBox.critical(self, self.tr("err"), self.tr("err_invalid_pkg_format"))
                return
                
            group_name = data["group_name"]
            items = data["items"]
            
            for item in items:
                self.db.add_history_item(item)
                
            groups = self.db.load_groups()
            base_name = group_name
            counter = 1
            while group_name in groups:
                group_name = f"{base_name} ({counter})"
                counter += 1
                
            groups[group_name] = items
            self.db.save_groups(groups)
            
            self.populate_library()
            QMessageBox.information(self, self.tr("success"), self.tr("import_success").format(group_name))
        except Exception as e:
            QMessageBox.critical(self, self.tr("err"), f"Import error:\n{e}")

    def export_package(self, group_name):
        groups = self.db.load_groups()
        if group_name not in groups: return
        group_items = groups[group_name]
        
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, self.tr("ctx_export_pkg"), f"{group_name}.json", "JSON Files (*.json)")
        if path:
            import json
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({"group_name": group_name, "items": group_items}, f, indent=4, ensure_ascii=False)
                QMessageBox.information(self, self.tr("success"), self.tr("export_success"))
            except Exception as e:
                QMessageBox.critical(self, self.tr("err"), f"Export error:\n{e}")

    def show_help(self):
        msg = QMessageBox(self)
        
        if self.lang == "ru":
            msg.setWindowTitle("Инструкция")
            help_text = """
<h3>Инструкция к SSH Model Manager</h3>

<b>1. Подключение (Вкладка 1)</b><br>
Подключение к удаленному серверу по SSH.
<ul>
  <li><b>SSH команда:</b> Вставьте команду (например: <code>ssh user@host -p 22</code>) и поля заполнятся автоматически.</li>
  <li><b>Авторизация:</b> Поддерживается вход по паролю и по SSH-ключу (включая ключи с паролем).</li>
  <li><b>Токены:</b> Для скачивания приватных моделей с Civitai или HuggingFace укажите токены в соответствующих полях перед скачиванием. Программа сама подставит их при обращении к сайтам.</li>
</ul>

<b>2. Загрузка (Вкладка 2)</b><br>
Управление загрузками файлов.
<ul>
  <li><b>Скачивание по ссылке:</b> Вставьте ссылку на модель. Выберите папку назначения в ComfyUI. Программа попытается определить оригинальное имя файла, но вы можете задать свое. Затем нажмите "Добавить в очередь".</li>
  <li><b>Загрузка с ПК (SFTP):</b> Перетащите файл модели с вашего компьютера в окно программы. Программа определит папку и подготовит файл. Файл будет отправлен на сервер через SFTP.</li>
  <li><b>Очередь:</b> Загрузки выполняются по очереди. Их можно ставить на паузу (<b>||</b>) и возобновлять (<b>►</b>). При отмене (<b>✕</b>) процесс прервется, а частичный недокачанный файл будет автоматически удален.</li>
</ul>

<b>3. Библиотека (Вкладка 3)</b><br>
Каталог моделей и управление файлами на сервере.
<ul>
  <li><b>Модели на сервере:</b> Программа автоматически сканирует папку <code>models</code> вашего сервера каждые 10 секунд. Можно обновить список вручную кнопкой "Обновить". Здесь отображаются найденные файлы моделей.</li>
  <li><b>Пакеты:</b> Отмечайте модели галочками и нажимайте "Создать пакет", чтобы сгруппировать их. Через пакет можно удобно и массово скачивать все нужные модели разом.</li>
  <li><b>Экспорт/Импорт:</b> ПКМ по пакету позволяет сохранить его в <code>.json</code> файл. Для импорта перетащите <code>.json</code> файл в окно программы или нажмите "📥 Импорт пакета".</li>
  <li><b>Удаление:</b> ПКМ по файлу или пакету открывает меню удаления. Вы можете удалить только файлы с сервера (оставив пакет в библиотеке), либо удалить и файлы, и сам пакет полностью.</li>
  <li><b>Массовая загрузка:</b> Выделите галочками файлы или целые пакеты в библиотеке и нажмите "Добавить выделенное в очередь" для их пакетного скачивания.</li>
</ul>
"""
        elif self.lang == "zh":
            msg.setWindowTitle("指南")
            help_text = """
<h3>SSH Model Manager 指南</h3>

<b>1. 连接 (标签页 1)</b><br>
通过 SSH 连接到您的远程服务器。
<ul>
  <li><b>SSH 命令:</b> 粘贴命令 (例如：<code>ssh user@host -p 22</code>) 即可自动填写字段。</li>
  <li><b>授权:</b> 支持密码和 SSH 密钥 (包括受密码保护的密钥) 登录。</li>
  <li><b>令牌 (Tokens):</b> 要从 Civitai 或 HuggingFace 下载私有模型，请在下载前在相应字段中输入您的令牌。程序将自动使用它们。</li>
</ul>

<b>2. 下载 (标签页 2)</b><br>
管理您的文件下载。
<ul>
  <li><b>通过链接下载:</b> 粘贴模型链接。在 ComfyUI 中选择目标文件夹。程序将尝试确定原始文件名，但您也可以自行设置。然后点击“添加到队列”。</li>
  <li><b>从电脑上传 (SFTP):</b> 将模型文件从您的电脑拖放到窗口中。程序将确定文件夹并准备文件。文件将通过 SFTP 上传到服务器。</li>
  <li><b>队列:</b> 下载将逐个进行。您可以暂停 (<b>||</b>) 和恢复 (<b>►</b>) 它们。如果取消 (<b>✕</b>)，进程将中止，任何未下载完成的碎片文件将被自动删除。</li>
</ul>

<b>3. 库 (标签页 3)</b><br>
模型目录和服务器文件管理。
<ul>
  <li><b>服务器上的模型:</b> 程序每 10 秒自动在后台扫描您服务器的 <code>models</code> 文件夹。您也可以使用“刷新”按钮手动更新列表。此处显示找到的模型文件。</li>
  <li><b>包 (Packages):</b> 勾选模型旁边的复选框，然后点击“创建包”将它们分组到一个列表中。通过包，您可以方便地批量下载所有需要的模型。</li>
  <li><b>导出/导入:</b> 右键单击一个包将其保存为 <code>.json</code> 文件。要导入，请将 <code>.json</code> 文件拖入窗口或点击“📥 导入包”。</li>
  <li><b>删除:</b> 右键单击文件或包以打开删除菜单。您可以选择仅从服务器删除文件（在库中保留包），或完全删除文件和包。</li>
  <li><b>批量下载:</b> 在库中勾选文件或整个包，然后点击“将所选添加到队列”进行批量下载。</li>
</ul>
"""
        else:
            msg.setWindowTitle("Help")
            help_text = """
<h3>SSH Model Manager Guide</h3>

<b>1. Connection (Tab 1)</b><br>
Connect to your remote server via SSH.
<ul>
  <li><b>SSH command:</b> Paste a command (e.g., <code>ssh user@host -p 22</code>) to automatically fill the fields.</li>
  <li><b>Authorization:</b> Password and SSH key (including password-protected keys) logins are supported.</li>
  <li><b>Tokens:</b> To download private models from Civitai or HuggingFace, enter your tokens in the respective fields before downloading. The program will automatically use them.</li>
</ul>

<b>2. Downloads (Tab 2)</b><br>
Manage your file downloads.
<ul>
  <li><b>Download by link:</b> Paste a model link. Choose the destination folder in ComfyUI. The program will try to determine the original filename, but you can set your own. Then click "Add to Queue".</li>
  <li><b>Upload from PC (SFTP):</b> Drag and drop a model file from your computer into the window. The program will determine the folder and prepare the file. The file will be uploaded to the server via SFTP.</li>
  <li><b>Queue:</b> Downloads run one by one. You can pause (<b>||</b>) and resume (<b>►</b>) them. If cancelled (<b>✕</b>), the process will abort and any partially downloaded file will be automatically deleted.</li>
</ul>

<b>3. Library (Tab 3)</b><br>
Model catalog and server file management.
<ul>
  <li><b>Models on server:</b> The program automatically scans your server's <code>models</code> folder every 10 seconds. You can also manually refresh the list using the "Refresh" button. Found model files are displayed here.</li>
  <li><b>Packages:</b> Check the boxes next to models and click "Create Package" to group them into a list. Through a package, you can conveniently and massively download all necessary models at once.</li>
  <li><b>Export/Import:</b> Right-click a package to save it to a <code>.json</code> file. To import, drag a <code>.json</code> file into the window or click "📥 Import Package".</li>
  <li><b>Deletion:</b> Right-click a file or package to open the deletion menu. You can choose to delete only the files from the server (keeping the package in the library), or delete both the files and the package entirely.</li>
  <li><b>Mass download:</b> Check files or entire packages in the library and click "Add Selected to Queue" to batch download them.</li>
</ul>
"""

        msg.setText(help_text)
        msg.setStyleSheet("QLabel{min-width: 600px;}")
        msg.exec()

    def do_mass_queue(self):
        if not self.ssh.connected:
            QMessageBox.warning(self, self.tr("err"), self.tr("err_no_ssh"))
            return
            
        added = 0
        with self.queue_lock:
            for node in self.history_items:
                if node.checkState(0) == Qt.CheckState.Checked:
                    data = node.data(0, Qt.ItemDataRole.UserRole)
                    if data.get("_is_group"):
                        for gi in data["items"]:
                            self.download_queue.append({"url": gi["url"], "filename": gi["filename"], "folder": gi["folder"]})
                            added += 1
                    else:
                        self.download_queue.append({"url": data["url"], "filename": data["filename"], "folder": data["folder"]})
                        added += 1
                        
        if added > 0:
            self.refresh_queue_ui()
            self.process_queue()
            self.tabs.setCurrentIndex(1)
            for node in self.history_items:
                node.setCheckState(0, Qt.CheckState.Unchecked)

if __name__ == "__main__":
    import ctypes
    try:
        myappid = 'sshmodelmanager.app.1.0'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(base_dir, "icon.png")
    
    app_icon = QIcon(icon_path)
    app.setWindowIcon(app_icon)
    
    window = SSHModelManager()
    window.setWindowIcon(app_icon)
    window.show()
    sys.exit(app.exec())
