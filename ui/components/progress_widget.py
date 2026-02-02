from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QProgressBar, QLabel, QGroupBox
from PySide6.QtCore import Qt, Slot
from typing import Optional

class ProgressWidget(QWidget):
    """
    MCCC: Reusable progress display component for generation tracking.
    Displays progress bar, ETA, and chapter statistics (Total/Passed/Failed).
    """
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self) -> None:
        """Initialize UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 5)
        layout.setSpacing(5)
        
        # Group Box
        group = QGroupBox("Generation Progress")
        group_layout = QVBoxLayout(group)
        
        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p% (%v/%m chunks)")
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #455A64;
                border-radius: 5px;
                text-align: center;
                height: 25px;
                background-color: #263238;
            }
            QProgressBar::chunk {
                background-color: #27AE60;
                border-radius: 3px;
            }
        """)
        group_layout.addWidget(self.progress_bar)
        
        # Statistics Row
        stats_layout = QHBoxLayout()
        
        # Total Chunks
        self.lbl_total = QLabel("Total: 0")
        self.lbl_total.setStyleSheet("font-weight: bold; color: #90CAF9;")
        stats_layout.addWidget(self.lbl_total)
        
        stats_layout.addStretch()
        
        # Passed Chunks
        self.lbl_passed = QLabel("✅ Passed: 0")
        self.lbl_passed.setStyleSheet("font-weight: bold; color: #27AE60;")
        stats_layout.addWidget(self.lbl_passed)
        
        stats_layout.addStretch()
        
        # Failed Chunks
        self.lbl_failed = QLabel("❌ Failed: 0")
        self.lbl_failed.setStyleSheet("font-weight: bold; color: #E74C3C;")
        stats_layout.addWidget(self.lbl_failed)
        
        group_layout.addLayout(stats_layout)
        
        # ETA Label
        self.lbl_eta = QLabel("ETA: Calculating...")
        self.lbl_eta.setAlignment(Qt.AlignCenter)
        self.lbl_eta.setStyleSheet("color: #FFA726; font-style: italic; margin-top: 5px;")
        group_layout.addWidget(self.lbl_eta)
        
        layout.addWidget(group)
    
    @Slot(int, int)
    def update_progress(self, completed: int, total: int) -> None:
        """
        Update progress bar.
        
        Args:
            completed: Number of chunks completed
            total: Total number of chunks
        """
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(completed)
        
        # Update format to show actual numbers
        if total > 0:
            percentage = int((completed / total) * 100)
            self.progress_bar.setFormat(f"{percentage}% ({completed}/{total} chunks)")
    
    @Slot(int, int, int)
    def update_stats(self, total: int, passed: int, failed: int) -> None:
        """
        Update statistics labels.
        
        Args:
            total: Total number of chunks
            passed: Number of chunks that passed ASR
            failed: Number of chunks that failed ASR
        """
        self.lbl_total.setText(f"Total: {total}")
        self.lbl_passed.setText(f"✅ Passed: {passed}")
        self.lbl_failed.setText(f"❌ Failed: {failed}")
    
    @Slot(float)
    def update_eta(self, seconds_remaining: float) -> None:
        """
        Update ETA display with formatted time.
        
        Args:
            seconds_remaining: Estimated seconds until completion
        """
        if seconds_remaining <= 0:
            self.lbl_eta.setText("ETA: Calculating...")
            return
        
        # Format time
        minutes, seconds = divmod(int(seconds_remaining), 60)
        hours, minutes = divmod(minutes, 60)
        
        if hours > 0:
            time_str = f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            time_str = f"{minutes}m {seconds}s"
        else:
            time_str = f"{seconds}s"
        
        self.lbl_eta.setText(f"ETA: {time_str}")
    
    def reset(self) -> None:
        """Reset all displays to initial state."""
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(100)
        self.lbl_total.setText("Total: 0")
        self.lbl_passed.setText("✅ Passed: 0")
        self.lbl_failed.setText("❌ Failed: 0")
        self.lbl_eta.setText("ETA: Calculating...")
