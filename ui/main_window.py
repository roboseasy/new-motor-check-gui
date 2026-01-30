import serial.tools.list_ports
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QIntValidator
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressDialog,
    QPushButton,
    QSlider,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from motor_controller import MotorController, MotorStatus


class ScanWorker(QThread):
    found = pyqtSignal(list)
    progress = pyqtSignal(int)

    def __init__(self, controller: MotorController, id_range: range):
        super().__init__()
        self._controller = controller
        self._id_range = id_range

    def run(self):
        found = []
        total = len(self._id_range)
        for i, motor_id in enumerate(self._id_range):
            try:
                if self._controller.ping(motor_id):
                    found.append(motor_id)
            except Exception:
                pass
            self.progress.emit(int((i + 1) / total * 100))
        self.found.emit(found)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("STS3215 Motor Test")
        self.setMinimumSize(600, 700)

        self._controller = MotorController()
        self._current_motor_id: int | None = None
        self._monitoring = False

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(8)

        layout.addWidget(self._build_connection_panel())
        layout.addWidget(self._build_motor_select_panel())
        layout.addWidget(self._build_control_panel())
        layout.addWidget(self._build_status_panel())
        layout.addWidget(self._build_log_panel())

        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._poll_status)

        self._set_controls_enabled(False)

    # ── Connection Panel ──

    def _build_connection_panel(self) -> QGroupBox:
        group = QGroupBox("연결")
        h = QHBoxLayout(group)

        h.addWidget(QLabel("포트:"))
        self._port_combo = QComboBox()
        self._port_combo.setMinimumWidth(200)
        h.addWidget(self._port_combo)

        refresh_btn = QPushButton("새로고침")
        refresh_btn.clicked.connect(self._refresh_ports)
        h.addWidget(refresh_btn)

        self._connect_btn = QPushButton("연결")
        self._connect_btn.clicked.connect(self._toggle_connection)
        h.addWidget(self._connect_btn)

        self._status_led = QLabel("●")
        self._status_led.setStyleSheet("color: red; font-size: 18px;")
        h.addWidget(self._status_led)

        h.addStretch()
        self._refresh_ports()
        return group

    # ── Motor Select Panel ──

    def _build_motor_select_panel(self) -> QGroupBox:
        group = QGroupBox("모터 선택")
        h = QHBoxLayout(group)

        self._scan_btn = QPushButton("모터 스캔")
        self._scan_btn.clicked.connect(self._scan_motors)
        h.addWidget(self._scan_btn)

        self._motor_combo = QComboBox()
        self._motor_combo.setMinimumWidth(100)
        self._motor_combo.currentTextChanged.connect(self._on_motor_selected)
        h.addWidget(self._motor_combo)

        h.addWidget(QLabel("ID 직접입력:"))
        self._motor_id_input = QSpinBox()
        self._motor_id_input.setRange(1, 253)
        self._motor_id_input.setValue(1)
        h.addWidget(self._motor_id_input)

        self._ping_btn = QPushButton("핑 테스트")
        self._ping_btn.clicked.connect(self._ping_motor)
        h.addWidget(self._ping_btn)

        select_btn = QPushButton("선택")
        select_btn.clicked.connect(self._select_manual_id)
        h.addWidget(select_btn)

        h.addStretch()
        return group

    # ── Control Panel ──

    def _build_control_panel(self) -> QGroupBox:
        group = QGroupBox("모터 제어")
        v = QVBoxLayout(group)

        # Position
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("위치 (0~4095):"))
        self._pos_slider = QSlider(Qt.Orientation.Horizontal)
        self._pos_slider.setRange(0, 4095)
        self._pos_slider.setValue(2048)
        self._pos_slider.valueChanged.connect(self._on_pos_slider_changed)
        row1.addWidget(self._pos_slider)
        self._pos_input = QSpinBox()
        self._pos_input.setRange(0, 4095)
        self._pos_input.setValue(2048)
        self._pos_input.valueChanged.connect(self._on_pos_input_changed)
        row1.addWidget(self._pos_input)
        self._move_btn = QPushButton("이동")
        self._move_btn.clicked.connect(self._move_motor)
        row1.addWidget(self._move_btn)
        v.addLayout(row1)

        # Speed
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("속도 (0~3400):"))
        self._speed_slider = QSlider(Qt.Orientation.Horizontal)
        self._speed_slider.setRange(0, 3400)
        self._speed_slider.setValue(1000)
        self._speed_slider.valueChanged.connect(self._on_speed_slider_changed)
        row2.addWidget(self._speed_slider)
        self._speed_input = QSpinBox()
        self._speed_input.setRange(0, 3400)
        self._speed_input.setValue(1000)
        self._speed_input.valueChanged.connect(self._on_speed_input_changed)
        row2.addWidget(self._speed_input)
        v.addLayout(row2)

        # Acceleration
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("가속도 (0~254):"))
        self._accel_slider = QSlider(Qt.Orientation.Horizontal)
        self._accel_slider.setRange(0, 254)
        self._accel_slider.setValue(50)
        self._accel_slider.valueChanged.connect(self._on_accel_slider_changed)
        row3.addWidget(self._accel_slider)
        self._accel_input = QSpinBox()
        self._accel_input.setRange(0, 254)
        self._accel_input.setValue(50)
        self._accel_input.valueChanged.connect(self._on_accel_input_changed)
        row3.addWidget(self._accel_input)
        v.addLayout(row3)

        # Buttons
        btn_row = QHBoxLayout()
        self._torque_btn = QPushButton("토크 ON")
        self._torque_btn.setCheckable(True)
        self._torque_btn.clicked.connect(self._toggle_torque)
        btn_row.addWidget(self._torque_btn)

        self._stop_btn = QPushButton("정지")
        self._stop_btn.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold;")
        self._stop_btn.clicked.connect(self._stop_motor)
        btn_row.addWidget(self._stop_btn)
        btn_row.addStretch()
        v.addLayout(btn_row)

        return group

    # ── Status Panel ──

    def _build_status_panel(self) -> QGroupBox:
        group = QGroupBox("상태 모니터")
        v = QVBoxLayout(group)

        grid = QHBoxLayout()
        self._status_labels: dict[str, QLabel] = {}
        for name, unit in [
            ("위치", ""),
            ("속도", ""),
            ("온도", "°C"),
            ("전압", "V"),
            ("전류", "mA"),
            ("부하", "%"),
        ]:
            frame = QFrame()
            frame.setFrameStyle(QFrame.Shape.StyledPanel)
            fl = QVBoxLayout(frame)
            title = QLabel(name)
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title.setStyleSheet("font-size: 11px; color: gray;")
            fl.addWidget(title)
            val = QLabel("--")
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val.setStyleSheet("font-size: 16px; font-weight: bold;")
            fl.addWidget(val)
            if unit:
                unit_label = QLabel(unit)
                unit_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                unit_label.setStyleSheet("font-size: 10px; color: gray;")
                fl.addWidget(unit_label)
            self._status_labels[name] = val
            grid.addWidget(frame)
        v.addLayout(grid)

        btn_row = QHBoxLayout()
        self._monitor_btn = QPushButton("모니터링 시작")
        self._monitor_btn.clicked.connect(self._toggle_monitoring)
        btn_row.addWidget(self._monitor_btn)

        self._read_once_btn = QPushButton("1회 읽기")
        self._read_once_btn.clicked.connect(self._read_status_once)
        btn_row.addWidget(self._read_once_btn)
        btn_row.addStretch()
        v.addLayout(btn_row)

        return group

    # ── Log Panel ──

    def _build_log_panel(self) -> QGroupBox:
        group = QGroupBox("로그")
        v = QVBoxLayout(group)
        self._log_text = QTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setMaximumHeight(120)
        v.addWidget(self._log_text)
        return group

    # ── Helpers ──

    def _log(self, msg: str):
        self._log_text.append(msg)

    def _set_controls_enabled(self, enabled: bool):
        for w in [
            self._scan_btn, self._ping_btn, self._move_btn,
            self._stop_btn, self._torque_btn, self._monitor_btn,
            self._read_once_btn, self._pos_slider, self._pos_input,
            self._speed_slider, self._speed_input, self._accel_slider,
            self._accel_input, self._motor_combo, self._motor_id_input,
        ]:
            w.setEnabled(enabled)

    def _update_status_display(self, status: MotorStatus):
        self._status_labels["위치"].setText(str(status.position))
        self._status_labels["속도"].setText(str(status.speed))
        self._status_labels["온도"].setText(str(status.temperature))
        self._status_labels["전압"].setText(f"{status.voltage:.1f}")
        self._status_labels["전류"].setText(f"{status.current:.0f}")
        self._status_labels["부하"].setText(str(status.load))

    # ── Slots ──

    def _refresh_ports(self):
        self._port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for p in ports:
            self._port_combo.addItem(f"{p.device} - {p.description}", p.device)
        if not ports:
            self._log("시리얼 포트를 찾을 수 없습니다.")

    def _toggle_connection(self):
        if self._controller.connected:
            self._controller.disconnect()
            self._connect_btn.setText("연결")
            self._status_led.setStyleSheet("color: red; font-size: 18px;")
            self._set_controls_enabled(False)
            self._stop_monitoring()
            self._log("연결 해제됨")
        else:
            port = self._port_combo.currentData()
            if not port:
                self._log("포트를 선택하세요.")
                return
            try:
                self._controller.connect(port)
                self._connect_btn.setText("연결 해제")
                self._status_led.setStyleSheet("color: #2ecc71; font-size: 18px;")
                self._set_controls_enabled(True)
                self._log(f"연결 성공: {port}")
            except Exception as e:
                self._log(f"연결 실패: {e}")

    def _scan_motors(self):
        if not self._controller.connected:
            return
        self._scan_btn.setEnabled(False)

        progress = QProgressDialog("모터 스캔 중...", "취소", 0, 100, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        self._scan_worker = ScanWorker(self._controller, range(1, 30))
        self._scan_worker.progress.connect(progress.setValue)

        def on_found(ids: list[int]):
            progress.close()
            self._motor_combo.clear()
            for mid in ids:
                self._motor_combo.addItem(f"ID: {mid}", mid)
            self._log(f"스캔 완료: {len(ids)}개 모터 발견 {ids}")
            self._scan_btn.setEnabled(True)

        self._scan_worker.found.connect(on_found)
        self._scan_worker.start()

    def _on_motor_selected(self, text: str):
        idx = self._motor_combo.currentIndex()
        if idx >= 0:
            self._current_motor_id = self._motor_combo.currentData()
            self._log(f"모터 선택: ID {self._current_motor_id}")

    def _select_manual_id(self):
        mid = self._motor_id_input.value()
        self._current_motor_id = mid
        self._log(f"모터 수동 선택: ID {mid}")

    def _ping_motor(self):
        mid = self._motor_id_input.value()
        try:
            result = self._controller.ping(mid)
            self._log(f"핑 ID {mid}: {'응답 있음' if result else '응답 없음'}")
        except Exception as e:
            self._log(f"핑 실패: {e}")

    # Slider <-> Input sync
    def _on_pos_slider_changed(self, val):
        self._pos_input.blockSignals(True)
        self._pos_input.setValue(val)
        self._pos_input.blockSignals(False)

    def _on_pos_input_changed(self, val):
        self._pos_slider.blockSignals(True)
        self._pos_slider.setValue(val)
        self._pos_slider.blockSignals(False)

    def _on_speed_slider_changed(self, val):
        self._speed_input.blockSignals(True)
        self._speed_input.setValue(val)
        self._speed_input.blockSignals(False)

    def _on_speed_input_changed(self, val):
        self._speed_slider.blockSignals(True)
        self._speed_slider.setValue(val)
        self._speed_slider.blockSignals(False)

    def _on_accel_slider_changed(self, val):
        self._accel_input.blockSignals(True)
        self._accel_input.setValue(val)
        self._accel_input.blockSignals(False)

    def _on_accel_input_changed(self, val):
        self._accel_slider.blockSignals(True)
        self._accel_slider.setValue(val)
        self._accel_slider.blockSignals(False)

    def _move_motor(self):
        if self._current_motor_id is None:
            self._log("모터를 먼저 선택하세요.")
            return
        pos = self._pos_input.value()
        speed = self._speed_input.value()
        accel = self._accel_input.value()
        try:
            self._controller.move_to(self._current_motor_id, pos, speed, accel)
            self._log(f"ID {self._current_motor_id} → 위치 {pos} (속도={speed}, 가속도={accel})")
        except Exception as e:
            self._log(f"이동 실패: {e}")

    def _stop_motor(self):
        if self._current_motor_id is None:
            return
        try:
            self._controller.stop(self._current_motor_id)
            self._log(f"ID {self._current_motor_id} 정지")
        except Exception as e:
            self._log(f"정지 실패: {e}")

    def _toggle_torque(self):
        if self._current_motor_id is None:
            return
        enable = self._torque_btn.isChecked()
        try:
            self._controller.set_torque(self._current_motor_id, enable)
            self._torque_btn.setText("토크 OFF" if enable else "토크 ON")
            self._log(f"ID {self._current_motor_id} 토크 {'ON' if enable else 'OFF'}")
        except Exception as e:
            self._log(f"토크 설정 실패: {e}")
            self._torque_btn.setChecked(not enable)

    def _toggle_monitoring(self):
        if self._monitoring:
            self._stop_monitoring()
        else:
            self._start_monitoring()

    def _start_monitoring(self):
        if self._current_motor_id is None:
            self._log("모터를 먼저 선택하세요.")
            return
        self._monitoring = True
        self._monitor_btn.setText("모니터링 중지")
        self._poll_timer.start(200)
        self._log("모니터링 시작")

    def _stop_monitoring(self):
        self._monitoring = False
        self._monitor_btn.setText("모니터링 시작")
        self._poll_timer.stop()
        self._log("모니터링 중지")

    def _poll_status(self):
        if self._current_motor_id is None:
            return
        try:
            status = self._controller.read_status(self._current_motor_id)
            self._update_status_display(status)
        except Exception:
            pass

    def _read_status_once(self):
        if self._current_motor_id is None:
            self._log("모터를 먼저 선택하세요.")
            return
        try:
            status = self._controller.read_status(self._current_motor_id)
            self._update_status_display(status)
            self._log(
                f"ID {self._current_motor_id} 상태: "
                f"위치={status.position}, 속도={status.speed}, "
                f"온도={status.temperature}°C, 전압={status.voltage}V, "
                f"전류={status.current}mA, 부하={status.load}%"
            )
        except Exception as e:
            self._log(f"상태 읽기 실패: {e}")
