"""
Offline Queue Manager using SQLite.
Stores images locally when cloud connection is unavailable.
"""

import os
import json
import sqlite3
import logging
import threading
from typing import Optional, Tuple, Dict, Any, List
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class OfflineQueue:
    """
    SQLite-based offline queue for storing images when offline.

    Features:
    - Persistent storage survives restarts
    - FIFO queue ordering
    - Automatic cleanup of old entries
    - Thread-safe operations
    - Configurable size limits
    """

    def __init__(
        self,
        db_path: str = "/var/lib/drone-ai/queue.db",
        max_size: int = 1000,
        max_age_hours: int = 72
    ):
        """
        Initialize offline queue.

        Args:
            db_path: Path to SQLite database
            max_size: Maximum number of entries
            max_age_hours: Maximum age of entries in hours
        """
        self.db_path = db_path
        self.max_size = max_size
        self.max_age_hours = max_age_hours

        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None

        # Ensure directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        # Initialize database
        self._init_db()

        logger.info(f"Offline queue initialized: {db_path}")

    def _init_db(self):
        """Initialize SQLite database."""
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

        cursor = self._conn.cursor()

        # Create queue table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                image_data BLOB NOT NULL,
                metadata TEXT,
                retry_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create index for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_queue_timestamp 
            ON queue(timestamp)
        """)

        self._conn.commit()

        # Cleanup old entries on startup
        self._cleanup()

    def add(self, image_data: bytes, metadata: Optional[Dict[str, Any]] = None) -> int:
        """
        Add image to queue.

        Args:
            image_data: JPEG image bytes
            metadata: Image metadata

        Returns:
            Queue entry ID
        """
        with self._lock:
            # Check size limit
            if self.size() >= self.max_size:
                # Remove oldest entry
                self._remove_oldest_locked()
                logger.warning("Queue full, removed oldest entry")

            cursor = self._conn.cursor()

            cursor.execute("""
                INSERT INTO queue (timestamp, image_data, metadata)
                VALUES (?, ?, ?)
            """, (
                datetime.utcnow().isoformat(),
                image_data,
                json.dumps(metadata) if metadata else None
            ))

            self._conn.commit()
            entry_id = cursor.lastrowid

            logger.debug(f"Added to queue: ID={entry_id}, size={len(image_data)} bytes")
            return entry_id

    def get_oldest(self) -> Optional[Tuple[bytes, Dict[str, Any]]]:
        """
        Get oldest entry from queue without removing it.

        Returns:
            Tuple of (image_data, metadata) or None
        """
        with self._lock:
            cursor = self._conn.cursor()

            cursor.execute("""
                SELECT id, image_data, metadata
                FROM queue
                ORDER BY id ASC
                LIMIT 1
            """)

            row = cursor.fetchone()

            if row:
                metadata = json.loads(row['metadata']) if row['metadata'] else {}
                return (row['image_data'], metadata)

            return None

    def remove_oldest(self) -> bool:
        """
        Remove oldest entry from queue.

        Returns:
            True if entry was removed
        """
        with self._lock:
            return self._remove_oldest_locked()

    def _remove_oldest_locked(self) -> bool:
        """Remove oldest entry (must hold lock)."""
        cursor = self._conn.cursor()

        cursor.execute("""
            DELETE FROM queue
            WHERE id = (
                SELECT id FROM queue ORDER BY id ASC LIMIT 1
            )
        """)

        self._conn.commit()
        return cursor.rowcount > 0

    def get_batch(self, limit: int = 10) -> List[Tuple[int, bytes, Dict[str, Any]]]:
        """
        Get batch of oldest entries.

        Args:
            limit: Maximum number of entries

        Returns:
            List of (id, image_data, metadata) tuples
        """
        with self._lock:
            cursor = self._conn.cursor()

            cursor.execute("""
                SELECT id, image_data, metadata
                FROM queue
                ORDER BY id ASC
                LIMIT ?
            """, (limit,))

            results = []
            for row in cursor.fetchall():
                metadata = json.loads(row['metadata']) if row['metadata'] else {}
                results.append((row['id'], row['image_data'], metadata))

            return results

    def remove_by_id(self, entry_id: int) -> bool:
        """
        Remove specific entry by ID.

        Args:
            entry_id: Entry ID to remove

        Returns:
            True if entry was removed
        """
        with self._lock:
            cursor = self._conn.cursor()

            cursor.execute("DELETE FROM queue WHERE id = ?", (entry_id,))
            self._conn.commit()

            return cursor.rowcount > 0

    def remove_batch(self, entry_ids: List[int]) -> int:
        """
        Remove multiple entries by ID.

        Args:
            entry_ids: List of entry IDs

        Returns:
            Number of entries removed
        """
        if not entry_ids:
            return 0

        with self._lock:
            cursor = self._conn.cursor()

            placeholders = ','.join('?' * len(entry_ids))
            cursor.execute(
                f"DELETE FROM queue WHERE id IN ({placeholders})",
                entry_ids
            )
            self._conn.commit()

            return cursor.rowcount

    def increment_retry(self, entry_id: int) -> int:
        """
        Increment retry count for an entry.

        Args:
            entry_id: Entry ID

        Returns:
            New retry count
        """
        with self._lock:
            cursor = self._conn.cursor()

            cursor.execute("""
                UPDATE queue
                SET retry_count = retry_count + 1
                WHERE id = ?
            """, (entry_id,))

            cursor.execute(
                "SELECT retry_count FROM queue WHERE id = ?",
                (entry_id,)
            )

            row = cursor.fetchone()
            self._conn.commit()

            return row['retry_count'] if row else 0

    def size(self) -> int:
        """
        Get number of entries in queue.

        Returns:
            Queue size
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM queue")
            return cursor.fetchone()['count']

    def total_size_bytes(self) -> int:
        """
        Get total size of queued images in bytes.

        Returns:
            Total size in bytes
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT SUM(LENGTH(image_data)) as total FROM queue")
            result = cursor.fetchone()['total']
            return result or 0

    def clear(self):
        """Clear all entries from queue."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("DELETE FROM queue")
            self._conn.commit()
            logger.info("Queue cleared")

    def _cleanup(self):
        """Remove entries older than max_age_hours."""
        with self._lock:
            cursor = self._conn.cursor()

            # Calculate cutoff time
            cutoff = datetime.utcnow().timestamp() - (self.max_age_hours * 3600)
            cutoff_iso = datetime.fromtimestamp(cutoff).isoformat()

            cursor.execute("""
                DELETE FROM queue
                WHERE timestamp < ?
            """, (cutoff_iso,))

            deleted = cursor.rowcount
            self._conn.commit()

            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old queue entries")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get queue statistics.

        Returns:
            Statistics dictionary
        """
        with self._lock:
            cursor = self._conn.cursor()

            # Count entries
            cursor.execute("SELECT COUNT(*) as count FROM queue")
            count = cursor.fetchone()['count']

            # Total size
            cursor.execute("SELECT SUM(LENGTH(image_data)) as total FROM queue")
            total_bytes = cursor.fetchone()['total'] or 0

            # Oldest entry
            cursor.execute("""
                SELECT timestamp FROM queue
                ORDER BY id ASC LIMIT 1
            """)
            oldest_row = cursor.fetchone()
            oldest = oldest_row['timestamp'] if oldest_row else None

            # Newest entry
            cursor.execute("""
                SELECT timestamp FROM queue
                ORDER BY id DESC LIMIT 1
            """)
            newest_row = cursor.fetchone()
            newest = newest_row['timestamp'] if newest_row else None

            # Retry stats
            cursor.execute("""
                SELECT AVG(retry_count) as avg, MAX(retry_count) as max
                FROM queue
            """)
            retry_row = cursor.fetchone()

            return {
                "count": count,
                "total_bytes": total_bytes,
                "total_mb": round(total_bytes / (1024 * 1024), 2),
                "max_size": self.max_size,
                "utilization": round(count / self.max_size * 100, 1),
                "oldest_entry": oldest,
                "newest_entry": newest,
                "avg_retries": round(retry_row['avg'] or 0, 2),
                "max_retries": retry_row['max'] or 0
            }

    def close(self):
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.info("Queue database closed")


class MemoryQueue:
    """
    In-memory queue for environments without persistent storage.

    Falls back to this if SQLite is not available.
    """

    def __init__(self, max_size: int = 100):
        """
        Initialize memory queue.

        Args:
            max_size: Maximum number of entries
        """
        self.max_size = max_size
        self._queue: List[Tuple[bytes, Dict[str, Any]]] = []
        self._lock = threading.Lock()

    def add(self, image_data: bytes, metadata: Optional[Dict[str, Any]] = None) -> int:
        """Add image to queue."""
        with self._lock:
            if len(self._queue) >= self.max_size:
                self._queue.pop(0)  # Remove oldest

            self._queue.append((image_data, metadata or {}))
            return len(self._queue) - 1

    def get_oldest(self) -> Optional[Tuple[bytes, Dict[str, Any]]]:
        """Get oldest entry."""
        with self._lock:
            if self._queue:
                return self._queue[0]
            return None

    def remove_oldest(self) -> bool:
        """Remove oldest entry."""
        with self._lock:
            if self._queue:
                self._queue.pop(0)
                return True
            return False

    def size(self) -> int:
        """Get queue size."""
        return len(self._queue)

    def clear(self):
        """Clear queue."""
        with self._lock:
            self._queue.clear()

    def close(self):
        """Cleanup (no-op for memory queue)."""
        pass