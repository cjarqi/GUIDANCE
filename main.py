#GUIDANCE/run.py
from mainsub import create_app 
from dotenv import load_dotenv
load_dotenv() 

app = create_app()
