"""Verificación biométrica de identidad — ¿la persona de la selfie es la misma de la cédula?

Usa los modelos ONNX de OpenCV Zoo, pensados para correr en CPU y ligeros:
  * **YuNet** (`FaceDetectorYN`, ~230 KB) detecta y alinea el rostro.
  * **SFace** (`FaceRecognizerSF`, ~37 MB) produce el embedding y compara por coseno.

Umbral recomendado por OpenCV para SFace: coseno >= 0.363 ⇒ misma identidad
(en pruebas, misma persona ~0.74, personas distintas ~0.10).

Diseño defensivo (patrón del resto del servicio): si falta `opencv-python` o los
modelos no están en disco (ni se pueden descargar), NUNCA aprueba a ciegas —
devuelve `decision="no_disponible"` para que el gate de emisión decida.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from .config import (FACE_DETECT_MODEL, FACE_MATCH_THRESHOLD, FACE_MODEL_BASE_URL,
                     FACE_MODEL_DIR, FACE_RECOG_MODEL)

log = logging.getLogger("seguria.identity")

# YuNet/SFace no son thread-safe (setInputSize muta el detector); FastAPI corre los
# endpoints sync en un threadpool, así que serializamos las llamadas al motor.
_LOCK = threading.Lock()
_ENGINE: dict[str, Any] | None = None   # {"detector", "recognizer"} cacheado
_ENGINE_TRIED = False

# Subcarpetas del OpenCV Zoo para la descarga de respaldo.
_ZOO_SUBDIR = {
    FACE_DETECT_MODEL: "face_detection_yunet",
    FACE_RECOG_MODEL: "face_recognition_sface",
}

DECISION_APROBADO = "aprobado"
DECISION_RECHAZADO = "rechazado"
DECISION_REVISION = "revision"        # hay imagen pero no se pudo comparar (rostro no hallado)
DECISION_NO_DISPONIBLE = "no_disponible"  # sin opencv/modelos: el motor no corrió


def _model_path(name: str) -> Path:
    return FACE_MODEL_DIR / name


def _ensure_model(name: str) -> Path | None:
    """Devuelve la ruta del modelo, descargándolo del Zoo si no está en disco."""
    path = _model_path(name)
    if path.is_file() and path.stat().st_size > 0:
        return path
    subdir = _ZOO_SUBDIR.get(name)
    if not subdir:
        return None
    url = f"{FACE_MODEL_BASE_URL.rstrip('/')}/{subdir}/{name}"
    try:
        import requests
        FACE_MODEL_DIR.mkdir(parents=True, exist_ok=True)
        log.info("descargando modelo facial %s desde %s", name, url)
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        path.write_bytes(r.content)
        return path if path.stat().st_size > 0 else None
    except Exception as exc:  # sin red/modelo → el motor queda no disponible
        log.warning("no se pudo obtener el modelo facial %s: %s", name, exc)
        return None


def _get_engine() -> dict[str, Any] | None:
    """Carga (una vez) YuNet + SFace. Devuelve None si opencv o los modelos faltan."""
    global _ENGINE, _ENGINE_TRIED
    if _ENGINE is not None:
        return _ENGINE
    if _ENGINE_TRIED:
        return None
    _ENGINE_TRIED = True
    try:
        import cv2  # noqa: F401
    except Exception as exc:
        log.warning("opencv no disponible; verificación de identidad deshabilitada (%s)", exc)
        return None
    det_path = _ensure_model(FACE_DETECT_MODEL)
    rec_path = _ensure_model(FACE_RECOG_MODEL)
    if not det_path or not rec_path:
        log.warning("modelos faciales ausentes; verificación de identidad deshabilitada")
        return None
    try:
        import cv2
        detector = cv2.FaceDetectorYN.create(str(det_path), "", (320, 320),
                                             score_threshold=0.7)
        recognizer = cv2.FaceRecognizerSF.create(str(rec_path), "")
        _ENGINE = {"detector": detector, "recognizer": recognizer}
        log.info("motor de identidad listo (YuNet + SFace, CPU)")
        return _ENGINE
    except Exception as exc:
        log.exception("no se pudo inicializar el motor facial: %s", exc)
        return None


def available() -> bool:
    """¿El motor biométrico está operativo (opencv + modelos)?"""
    return _get_engine() is not None


def _read_image(path: str):
    import cv2
    img = cv2.imread(str(path))
    return img


def _best_face(engine: dict[str, Any], img):
    """Detecta rostros y devuelve (feature, score_deteccion) del rostro más confiable."""
    import numpy as np
    detector = engine["detector"]
    recognizer = engine["recognizer"]
    h, w = img.shape[:2]
    detector.setInputSize((w, h))
    _n, faces = detector.detect(img)
    if faces is None or len(faces) == 0:
        return None, 0.0
    face = faces[int(np.argmax(faces[:, -1]))]  # mayor score de detección
    aligned = recognizer.alignCrop(img, face)
    feature = recognizer.feature(aligned)
    return feature, float(face[-1])


def verify(doc_path: str, selfie_path: str, *,
           threshold: float | None = None) -> dict[str, Any]:
    """Compara el rostro de la cédula (doc_path) con la selfie (selfie_path).

    Devuelve un veredicto auditable: {available, decision, score, threshold, method,
    doc_face_score, selfie_face_score, reasons}. Nunca lanza excepción."""
    thr = FACE_MATCH_THRESHOLD if threshold is None else float(threshold)
    base = {"available": False, "decision": DECISION_NO_DISPONIBLE, "score": None,
            "threshold": thr, "method": "yunet_sface", "doc_face_score": None,
            "selfie_face_score": None, "reasons": []}

    engine = _get_engine()
    if engine is None:
        base["reasons"] = ["motor biométrico no disponible (opencv/modelos ausentes)"]
        return base

    try:
        import cv2
        with _LOCK:
            doc_img = _read_image(doc_path)
            selfie_img = _read_image(selfie_path)
            if doc_img is None or selfie_img is None:
                base["available"] = True
                base["decision"] = DECISION_REVISION
                miss = []
                if doc_img is None:
                    miss.append("no se pudo leer la imagen de la cédula")
                if selfie_img is None:
                    miss.append("no se pudo leer la selfie")
                base["reasons"] = miss
                return base

            doc_feat, doc_score = _best_face(engine, doc_img)
            selfie_feat, selfie_score = _best_face(engine, selfie_img)
            base["available"] = True
            base["doc_face_score"] = round(doc_score, 3) if doc_feat is not None else None
            base["selfie_face_score"] = round(selfie_score, 3) if selfie_feat is not None else None

            reasons = []
            if doc_feat is None:
                reasons.append("no se detectó un rostro claro en la foto de la cédula")
            if selfie_feat is None:
                reasons.append("no se detectó un rostro claro en la selfie")
            if reasons:
                base["decision"] = DECISION_REVISION
                base["reasons"] = reasons
                return base

            score = float(engine["recognizer"].match(
                doc_feat, selfie_feat, cv2.FaceRecognizerSF_FR_COSINE))
            base["score"] = round(score, 3)
            if score >= thr:
                base["decision"] = DECISION_APROBADO
                base["reasons"] = [f"coincidencia facial {score:.3f} ≥ umbral {thr:.3f}"]
            else:
                base["decision"] = DECISION_RECHAZADO
                base["reasons"] = [f"coincidencia facial {score:.3f} < umbral {thr:.3f}: "
                                   "el rostro de la selfie no coincide con el de la cédula"]
            return base
    except Exception as exc:  # cualquier fallo del motor → revisión, nunca aprobación
        log.exception("fallo verificando identidad: %s", exc)
        base["available"] = True
        base["decision"] = DECISION_REVISION
        base["reasons"] = [f"error del motor biométrico: {exc}"]
        return base
