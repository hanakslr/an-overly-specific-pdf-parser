from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# Allow frontend to fetch from browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

doc_state: dict = {
    "type": "doc",
    "content": [
        {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": "Hello from Python!"},
            ],
        },
    ],
}


class DocPayload(BaseModel):
    doc: Any


@app.get("/api/get-doc")
def get_doc():
    return {"content": doc_state}


@app.post("/api/update-doc")
def update_doc(payload: DocPayload):
    global doc_state
    doc_state = payload.doc
    return {"status": "ok"}


class AppendPayload(BaseModel):
    new_nodes: list[Any]


@app.post("/api/append-to-doc")
def append_to_doc(payload: AppendPayload):
    global doc_state
    print(f"Recieved {payload}")
    doc_state["content"].extend(payload.new_nodes)
    return {"status": "ok"}
