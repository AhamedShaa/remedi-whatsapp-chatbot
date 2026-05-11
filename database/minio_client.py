import asyncio
import io
from datetime import datetime, timedelta
from functools import partial

from minio import Minio
from minio.error import S3Error

from config.settings import settings
from utils.logger import logger


class MinIOError(Exception):
    pass


class MinIOClient:
    def __init__(self) -> None:
        self._client: Minio | None = None

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Initialise the Minio client and ensure both application buckets exist.

        Buckets are private by default — no explicit policy is set, which leaves
        the MinIO default (no public access) in place.
        """
        try:
            self._client = Minio(
                settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure,
            )
            loop = asyncio.get_event_loop()
            for bucket in (settings.minio_bucket_reports, settings.minio_bucket_pdfs):
                await loop.run_in_executor(None, partial(self._ensure_bucket, bucket))
            logger.info("MinIO connected; buckets verified")
        except MinIOError:
            raise
        except Exception as exc:
            raise MinIOError(f"MinIO initialisation failed: {exc}") from exc

    def _ensure_bucket(self, bucket: str) -> None:
        if not self._client.bucket_exists(bucket):
            self._client.make_bucket(bucket)
            logger.info(f"MinIO: created bucket '{bucket}'")
        else:
            logger.debug(f"MinIO: bucket '{bucket}' already exists")

    # ── Operations ───────────────────────────────────────────────────────────

    async def upload_report(
        self,
        patient_id: str,
        file_bytes: bytes,
        mime_type: str,
        report_id: str,
    ) -> str:
        """Upload a lab report and return the object name (not a public URL).

        Object name: ``{patient_id}/{report_id}.pdf``
        """
        object_name = f"{patient_id}/{report_id}.pdf"
        metadata = {
            "patient-id": patient_id,
            "report-id": report_id,
            "upload-timestamp": datetime.utcnow().isoformat(),
        }

        def _put() -> None:
            self._client.put_object(
                settings.minio_bucket_reports,
                object_name,
                io.BytesIO(file_bytes),
                length=len(file_bytes),
                content_type=mime_type,
                metadata=metadata,
            )

        try:
            await asyncio.get_event_loop().run_in_executor(None, _put)
            logger.info(f"MinIO: uploaded {object_name}")
            return object_name
        except S3Error as exc:
            raise MinIOError(f"Upload failed for {object_name}: {exc}") from exc

    async def get_report_url(self, object_name: str, expires_minutes: int = 10) -> str:
        """Return a presigned GET URL that expires after ``expires_minutes``.

        Doctors use this URL to view reports without needing direct MinIO access.
        """
        def _presign() -> str:
            return self._client.presigned_get_object(
                settings.minio_bucket_reports,
                object_name,
                expires=timedelta(minutes=expires_minutes),
            )

        try:
            url: str = await asyncio.get_event_loop().run_in_executor(None, _presign)
            return url
        except S3Error as exc:
            raise MinIOError(f"Presign failed for {object_name}: {exc}") from exc

    async def download_report(self, object_name: str) -> bytes:
        """Download and return raw bytes for a stored report.

        Used when re-analysing an existing report through the AI pipeline.
        """
        def _get() -> bytes:
            response = self._client.get_object(settings.minio_bucket_reports, object_name)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()

        try:
            return await asyncio.get_event_loop().run_in_executor(None, _get)
        except S3Error as exc:
            raise MinIOError(f"Download failed for {object_name}: {exc}") from exc

    # ── Health ───────────────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        """Return True if MinIO is reachable, False otherwise."""
        if self._client is None:
            return False
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, self._client.list_buckets
            )
            return True
        except Exception:
            return False


minio_client = MinIOClient()
