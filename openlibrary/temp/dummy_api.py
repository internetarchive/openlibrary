from fastapi import FastAPI 


app = FastAPI() 

@app.get("/")
async def return_json():
    return {
            "status": "OK",
            "latest_uid": 3,
            "rows": [
            {
                "time": "2026-05-01 16:50:29",
                "identifier": "completeworksofm21twai",
                "username": "@XXX",
                "loan_id": "5bb9565114ff108cff50d2417f4b85c14ae67c42",
                "event_type": "expire_browse",
                "extra": "{\"userid\":\"@XXX\",\"listname\":\"loan\",\"identifier\":\"completeworksofm21twai\",\"updatedate\":\"2026-05-01 14:42:43\",\"created\":\"2026-05-01 14:42:43\",\"id\":\"3888614424\",\"type\":\"SESSION_LOAN\",\"until\":\"2026-07-03 15:42:43\"}",
                "uid": 3
            }
            ]
            }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)