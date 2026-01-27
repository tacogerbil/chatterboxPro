from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QSlider, QDoubleSpinBox
from PySide6.QtCore import Qt, Signal

class QLabeledSlider(QWidget):
    """
    A Qt equivalent of the Tkinter LabeledSlider.
    Layout: [Label] [Slider] [SpinBox]
    """
    value_changed = Signal(float)

    def __init__(self, label_text: str, from_val: float, to_val: float, 
                 initial_val: float = 0.0, step: float = 0.1, 
                 left_label: str = None, right_label: str = None, parent=None):
        super().__init__(parent)
        
        # Main Layout: Vertical to stack (Slider+Value) over (Helper Labels)
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(2)
        
        # Top Row: Label | Slider | SpinBox
        self.top_row_widget = QWidget()
        self.top_layout = QHBoxLayout(self.top_row_widget)
        self.top_layout.setContentsMargins(0, 0, 0, 0)
        
        # Label
        self.label = QLabel(label_text)
        self.label.setMinimumWidth(120)
        
        # Slider
        self.slider = QSlider(Qt.Horizontal)
        self.scale_factor = 100 if step < 1 else 10 # Increase precision for step=1
        self.slider.setRange(int(from_val * self.scale_factor), int(to_val * self.scale_factor))
        self.slider.setValue(int(initial_val * self.scale_factor))
        
        # SpinBox
        self.spinbox = QDoubleSpinBox()
        self.spinbox.setRange(from_val, to_val)
        self.spinbox.setSingleStep(step)
        self.spinbox.setValue(initial_val)
        
        self.top_layout.addWidget(self.label)
        self.top_layout.addWidget(self.slider)
        self.top_layout.addWidget(self.spinbox)
        
        self.main_layout.addWidget(self.top_row_widget)
        
        # Helper Labels Row (if provided)
        if left_label or right_label:
            self.helper_widget = QWidget()
            self.helper_layout = QHBoxLayout(self.helper_widget)
            self.helper_layout.setContentsMargins(125, 0, 50, 0) # Indent to align under slider
            
            l_lbl = QLabel(left_label or "")
            l_lbl.setStyleSheet("color: gray; font-size: 10px;")
            r_lbl = QLabel(right_label or "")
            r_lbl.setStyleSheet("color: gray; font-size: 10px;")
            r_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            
            self.helper_layout.addWidget(l_lbl)
            self.helper_layout.addStretch()
            self.helper_layout.addWidget(r_lbl)
            
            self.main_layout.addWidget(self.helper_widget)

        # Connect Signals
        self.slider.valueChanged.connect(self._on_slider_change)
        self.spinbox.valueChanged.connect(self._on_spinbox_change)
        
    def _on_slider_change(self, val):
        float_val = val / self.scale_factor
        self.spinbox.blockSignals(True)
        self.spinbox.setValue(float_val)
        self.spinbox.blockSignals(False)
        self.value_changed.emit(float_val)
        
    def _on_spinbox_change(self, val):
        int_val = int(val * self.scale_factor)
        self.slider.blockSignals(True)
        self.slider.setValue(int_val)
        self.slider.blockSignals(False)
        self.value_changed.emit(val)

    def set_value(self, val):
        self.spinbox.setValue(val)
        
    def get_value(self):
        return self.spinbox.value()
