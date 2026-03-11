from typing import Optional
import pandas as pd

class AppState:
    def __init__(self):
        self.df: Optional[pd.DataFrame] = None
        self.df_hydra = None
        self.hydra_path = None
        
        self.cfg = None
        self.machine_cfg = None
        
        self.table_frame = None
        
        self.last_report_tetx: str = ""
        self.last_report_data = None
        self.last_report_kind: Optional[str] = None
        
        self.production_calculated: bool = False
        
        