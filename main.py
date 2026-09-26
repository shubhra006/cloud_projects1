import os

import boto3
import shortuuid

from datetime import datetime, timezone
from typing import List

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient


# --------------------------------------------------
# Load environment variables
# --------------------------------------------------

load_dotenv()


# --------------------------------------------------
# FastAPI
# --------------------------------------------------

app = FastAPI()


# --------------------------------------------------
# CORS
# --------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten this later for production
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------
# AWS S3
# --------------------------------------------------

s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION"),
)

BUCKET = os.getenv("S3_BUCKET_NAME")


# --------------------------------------------------
# MongoDB
# --------------------------------------------------

client = MongoClient(os.getenv("MONGO_URI"))

db = client["share_platform"]

shares = db["shares"]


# --------------------------------------------------
# Upload files
# --------------------------------------------------

@app.post("/upload")
async def upload_files(files: List[UploadFile] = File(...)):

    # Generate unique 8-character share ID
    share_id = shortuuid.ShortUUID().random(length=8)

    uploaded = []

    # Upload every file to S3
    for file in files:

        # Example:
        # abc12345/a.jpeg
        # abc12345/b.JPG

        key = f"{share_id}/{file.filename}"

        s3.upload_fileobj(
            file.file,
            BUCKET,
            key
        )

        uploaded.append(
            {
                "filename": file.filename,
                "s3_key": key,
                "content_type": file.content_type,
            }
        )

    # --------------------------------------------------
    # Save information in MongoDB
    # --------------------------------------------------

    doc = {
        "_id": share_id,
        "created_at": datetime.now(timezone.utc),
        "files": uploaded,
    }

    shares.insert_one(doc)

    # --------------------------------------------------
    # Response
    # --------------------------------------------------

    return {
        "share_id": share_id,
        "files": uploaded,
    }


# --------------------------------------------------
# Get share information
# --------------------------------------------------

@app.get("/share/{share_id}")
async def get_share(share_id: str):

    # Find share in MongoDB
    doc = shares.find_one(
        {
            "_id": share_id
        }
    )

    # Share doesn't exist
    if not doc:
        raise HTTPException(
            status_code=404,
            detail="Share ID not found"
        )

    files_with_urls = []

    # Generate temporary S3 URLs
    for file in doc["files"]:

        url = s3.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": BUCKET,
                "Key": file["s3_key"],
            },
            ExpiresIn=3600,  # 1 hour
        )

        files_with_urls.append(
            {
                "filename": file["filename"],
                "content_type": file["content_type"],
                "download_url": url,
            }
        )

    return {
        "share_id": share_id,
        "files": files_with_urls,
    }