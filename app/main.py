from fastapi import FastAPI

app = FastAPI(title='Food Safety AI Agent')

@app.get('/')
def root():
    return {'status':'ok','project':'Food Safety AI Agent'}

@app.get('/health')
def health():
    return {'healthy': True}
