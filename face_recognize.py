"""Server-side face embedding and matching service."""

import json

import cv2
import numpy as np
from insightface.app import FaceAnalysis


class FaceRecognitionService:
    """Load the registered face database and match uploaded camera frames."""

    def __init__(self, db_path, similarity_threshold=0.35):
        self.db_path = db_path
        self.similarity_threshold = float(similarity_threshold)
        with open(self.db_path, "r", encoding="utf-8") as database_file:
            self.face_database = json.load(database_file)
        if not isinstance(self.face_database, dict) or not self.face_database:
            raise ValueError("人脸库为空或格式无效")

        self.model = FaceAnalysis(
            name="buffalo_l",
            providers=["CPUExecutionProvider"],
        )
        self.model.prepare(ctx_id=-1, det_size=(320, 320), det_thresh=0.85)

    def recognize(self, image_bytes):
        """Return the best matching name, or ``None`` when no match is found."""
        image_array = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("上传的图片无法读取")

        faces = self.model.get(image)
        best_name = None
        best_similarity = self.similarity_threshold

        for face in sorted(faces, key=lambda item: item.det_score, reverse=True)[:3]:
            embedding = face.embedding.astype(np.float32)
            embedding /= np.linalg.norm(embedding) + 1e-7

            for record in self.face_database.values():
                if not isinstance(record, dict):
                    continue
                name = record.get("name")
                features = record.get("features")
                if not isinstance(name, str) or not name.strip() or not isinstance(features, list):
                    continue

                database_embedding = np.asarray(features, dtype=np.float32)
                if database_embedding.shape != embedding.shape:
                    continue
                database_embedding /= np.linalg.norm(database_embedding) + 1e-7
                similarity = float(np.dot(embedding, database_embedding))
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_name = name

        return best_name
