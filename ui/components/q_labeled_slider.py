from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSlider, QDoubleSpinBox
from PySide6.QtCore import Qt, Signal

class QLabeledSlider(QWidget):
    """
    A Qt equivalent of the Tkinter LabeledSlider.
    Layout: [Label] [Slider] [SpinBox]
    """
    value_changed = Signal(float)

    def __init__(self, label_text: str, from_val: float, to_val: float, 
                 initial_val: float = 0.0, step: float = 0.1, parent=None):
        super().__init__(parent)
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # Label
        self.label = QLabel(label_text)
        self.label.setMinimumWidth(120)
        
        # Slider (Integer based, so we scale it)
        self.slider = QSlider(Qt.Horizontal)
        self.scale_factor = 100 if step < 1 else 1
        self.slider.setRange(int(from_val * self.scale_factor), int(to_val * self.scale_factor))
        self.slider.setValue(int(initial_val * self.scale_factor))
        
        # SpinBox (Double)
        self.spinbox = QDoubleSpinBox()
        self.spinbox.setRange(from_val, to_val)
        self.spinbox.setSingleStep(step)
        self.spinbox.setValue(initial_val)
        
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.slider)
        self.layout.addWidget(self.spinbox)
        
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
