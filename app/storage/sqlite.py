import aiosqlite
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.schemas.task import TaskDB, TaskStatus


class SQLiteStorage:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None

    async def init(self):
        """Initialize database and create tables"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(self.db_path)
        await self._create_tables()

    async def close(self):
        """Close database connection"""
        if self._connection:
            await self._connection.close()
            self._connection = None

    async def _create_tables(self):
        """Create necessary tables"""
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                progress INTEGER DEFAULT 0,
                workflow TEXT NOT NULL,
                output_node_ids TEXT NOT NULL,
                feishu_config TEXT NOT NULL,
                result TEXT,
                error TEXT,
                metadata TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)
        """)
        await self._connection.commit()

    async def create_task(self, task: TaskDB) -> TaskDB:
        """Create a new task"""
        await self._connection.execute(
            """
            INSERT INTO tasks (
                task_id, status, progress, workflow, output_node_ids,
                feishu_config, result, error, metadata, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task.task_id,
                task.status.value,
                task.progress,
                json.dumps(task.workflow),
                json.dumps(task.output_node_ids),
                json.dumps(task.feishu_config),
                json.dumps(task.result) if task.result else None,
                task.error,
                json.dumps(task.metadata) if task.metadata else None,
                task.created_at.isoformat(),
                task.updated_at.isoformat(),
            )
        )
        await self._connection.commit()
        return task

    async def get_task(self, task_id: str) -> Optional[TaskDB]:
        """Get a task by ID"""
        async with self._connection.execute(
            "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return self._row_to_task(row)
            return None

    async def update_task(
        self,
        task_id: str,
        status: Optional[TaskStatus] = None,
        progress: Optional[int] = None,
        result: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> Optional[TaskDB]:
        """Update task fields"""
        updates = []
        params = []

        if status is not None:
            updates.append("status = ?")
            params.append(status.value)

        if progress is not None:
            updates.append("progress = ?")
            params.append(progress)

        if result is not None:
            updates.append("result = ?")
            params.append(json.dumps(result))

        if error is not None:
            updates.append("error = ?")
            params.append(error)

        updates.append("updated_at = ?")
        params.append(datetime.utcnow().isoformat())
        params.append(task_id)

        await self._connection.execute(
            f"UPDATE tasks SET {', '.join(updates)} WHERE task_id = ?",
            params
        )
        await self._connection.commit()
        return await self.get_task(task_id)

    async def delete_task(self, task_id: str) -> bool:
        """Delete a task"""
        cursor = await self._connection.execute(
            "DELETE FROM tasks WHERE task_id = ?", (task_id,)
        )
        await self._connection.commit()
        return cursor.rowcount > 0

    async def get_pending_tasks(self, limit: int = 10) -> list[TaskDB]:
        """Get pending tasks for processing"""
        async with self._connection.execute(
            """
            SELECT * FROM tasks
            WHERE status = ?
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (TaskStatus.PENDING.value, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_task(row) for row in rows]

    def _row_to_task(self, row: tuple) -> TaskDB:
        """Convert database row to TaskDB model"""
        return TaskDB(
            task_id=row[0],
            status=TaskStatus(row[1]),
            progress=row[2],
            workflow=json.loads(row[3]),
            output_node_ids=json.loads(row[4]),
            feishu_config=json.loads(row[5]),
            result=json.loads(row[6]) if row[6] else None,
            error=row[7],
            metadata=json.loads(row[8]) if row[8] else None,
            created_at=datetime.fromisoformat(row[9]),
            updated_at=datetime.fromisoformat(row[10]),
        )


_storage: Optional[SQLiteStorage] = None


async def get_storage() -> SQLiteStorage:
    """Get the global storage instance"""
    global _storage
    if _storage is None:
        raise RuntimeError("Storage not initialized. Call init_storage first.")
    return _storage


async def init_storage(db_path: str) -> SQLiteStorage:
    """Initialize the global storage instance"""
    global _storage
    _storage = SQLiteStorage(db_path)
    await _storage.init()
    return _storage


async def close_storage():
    """Close the global storage instance"""
    global _storage
    if _storage:
        await _storage.close()
        _storage = None
