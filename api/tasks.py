"""
Tasks domain endpoints
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Body
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from datetime import date, datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict, EmailStr, field_validator

import models
import validators
from config import settings
from database import get_db
from dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Tasks"])

class TaskCreate(BaseModel):
    """Schema for creating a task"""
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    priority: Optional[str] = Field(default="MEDIUM")
    assigned_to: Optional[int] = None
    due_date: Optional[date] = None
    kindergarten_id: Optional[int] = None


class TaskUpdate(BaseModel):
    """Schema for updating a task"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assigned_to: Optional[int] = None
    due_date: Optional[date] = None


class TaskResponse(BaseModel):
    """Schema for task response"""
    id: int
    kindergarten_id: int
    title: str
    description: Optional[str]
    status: str
    priority: str
    assigned_to: Optional[int]
    created_by: int
    due_date: Optional[date]
    completed_at: Optional[datetime]
    created_at: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)


@router.post("/tasks", status_code=status.HTTP_201_CREATED, response_model=TaskResponse)
def create_task(
    task_data: TaskCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new task"""
    # Validate role - only admin, manager, supervisor can create tasks
    if current_user.role not in [models.UserRole.ADMIN, models.UserRole.MANAGER, models.UserRole.SUPERVISOR]:
        raise HTTPException(status_code=403, detail="Not authorized to create tasks")
    
    # Resolve kindergarten: admins may optionally specify one; others use their assigned one
    if current_user.role == models.UserRole.ADMIN:
        if task_data.kindergarten_id:
            kindergarten = db.query(models.Kindergarten).filter(
                models.Kindergarten.id == task_data.kindergarten_id
            ).first()
            if not kindergarten:
                raise HTTPException(status_code=404, detail="Kindergarten not found")
            kindergarten_id = kindergarten.id
        else:
            # Fall back to first active kindergarten for admin-level tasks
            kindergarten = db.query(models.Kindergarten).filter(
                models.Kindergarten.status == models.KindergartenStatus.ACTIVE
            ).first()
            if not kindergarten:
                raise HTTPException(status_code=400, detail="No active kindergarten found; please provide kindergarten_id")
            kindergarten_id = kindergarten.id
    else:
        if not current_user.kindergarten_id:
            raise HTTPException(status_code=400, detail="User not assigned to a kindergarten")
        kindergarten_id = current_user.kindergarten_id
    
    # Validate priority
    priority_str = task_data.priority.upper() if task_data.priority else "MEDIUM"
    try:
        priority = models.TaskPriority(priority_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid priority: {task_data.priority}. Valid values: LOW, MEDIUM, HIGH, URGENT")
    
    # Create task
    task = models.Task(
        kindergarten_id=kindergarten_id,
        title=task_data.title,
        description=task_data.description,
        priority=priority,
        status=models.TaskStatus.PENDING,
        assigned_to=task_data.assigned_to,
        created_by=current_user.id,
        due_date=task_data.due_date
    )
    
    db.add(task)
    db.commit()
    db.refresh(task)
    
    return TaskResponse(
        id=task.id,
        kindergarten_id=task.kindergarten_id,
        title=task.title,
        description=task.description,
        status=task.status.value,
        priority=task.priority.value,
        assigned_to=task.assigned_to,
        created_by=task.created_by,
        due_date=task.due_date,
        completed_at=task.completed_at,
        created_at=task.created_at
    )


@router.get("/tasks", response_model=List[TaskResponse])
def get_tasks(
    status_filter: Optional[str] = None,
    priority_filter: Optional[str] = None,
    assigned_to_me: bool = False,
    created_by_me: bool = False,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all tasks with optional filters"""
    query = db.query(models.Task)
    
    # Filter by kindergarten for non-admin users
    if current_user.role != models.UserRole.ADMIN and current_user.kindergarten_id:
        query = query.filter(models.Task.kindergarten_id == current_user.kindergarten_id)
    
    if status_filter:
        try:
            status_enum = models.TaskStatus(status_filter.upper())
            query = query.filter(models.Task.status == status_enum)
        except ValueError:
            logger.warning("INVALID_FILTER status_filter=%r ignored — not a valid TaskStatus", status_filter)

    if priority_filter:
        try:
            priority_enum = models.TaskPriority(priority_filter.upper())
            query = query.filter(models.Task.priority == priority_enum)
        except ValueError:
            logger.warning("INVALID_FILTER priority_filter=%r ignored — not a valid TaskPriority", priority_filter)
    
    if assigned_to_me:
        query = query.filter(models.Task.assigned_to == current_user.id)
    
    if created_by_me:
        query = query.filter(models.Task.created_by == current_user.id)
    
    tasks = query.order_by(models.Task.created_at.desc()).all()
    
    return [
        TaskResponse(
            id=t.id,
            kindergarten_id=t.kindergarten_id,
            title=t.title,
            description=t.description,
            status=t.status.value,
            priority=t.priority.value,
            assigned_to=t.assigned_to,
            created_by=t.created_by,
            due_date=t.due_date,
            completed_at=t.completed_at,
            created_at=t.created_at
        )
        for t in tasks
    ]


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(
    task_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific task by ID"""
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Check access
    if current_user.role != models.UserRole.ADMIN:
        if task.kindergarten_id != current_user.kindergarten_id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    return TaskResponse(
        id=task.id,
        kindergarten_id=task.kindergarten_id,
        title=task.title,
        description=task.description,
        status=task.status.value,
        priority=task.priority.value,
        assigned_to=task.assigned_to,
        created_by=task.created_by,
        due_date=task.due_date,
        completed_at=task.completed_at,
        created_at=task.created_at
    )


@router.put("/tasks/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: int,
    task_data: TaskUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an existing task"""
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Check access
    if current_user.role != models.UserRole.ADMIN:
        if task.kindergarten_id != current_user.kindergarten_id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Update fields
    if task_data.title is not None:
        task.title = task_data.title
    if task_data.description is not None:
        task.description = task_data.description
    if task_data.status is not None:
        try:
            new_status = models.TaskStatus(task_data.status.upper())
            task.status = new_status
            if new_status == models.TaskStatus.COMPLETED:
                task.completed_at = datetime.now()
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {task_data.status}")
    if task_data.priority is not None:
        try:
            task.priority = models.TaskPriority(task_data.priority.upper())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid priority: {task_data.priority}")
    if task_data.assigned_to is not None:
        task.assigned_to = task_data.assigned_to
    if task_data.due_date is not None:
        task.due_date = task_data.due_date
    
    db.commit()
    db.refresh(task)
    
    return TaskResponse(
        id=task.id,
        kindergarten_id=task.kindergarten_id,
        title=task.title,
        description=task.description,
        status=task.status.value,
        priority=task.priority.value,
        assigned_to=task.assigned_to,
        created_by=task.created_by,
        due_date=task.due_date,
        completed_at=task.completed_at,
        created_at=task.created_at
    )


@router.post("/tasks/{task_id}/toggle", response_model=TaskResponse)
def toggle_task_status(
    task_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Toggle task between PENDING and COMPLETED"""
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Check access
    if current_user.role != models.UserRole.ADMIN:
        if task.kindergarten_id != current_user.kindergarten_id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Toggle status
    if task.status == models.TaskStatus.COMPLETED:
        task.status = models.TaskStatus.PENDING
        task.completed_at = None
    else:
        task.status = models.TaskStatus.COMPLETED
        task.completed_at = datetime.now()
    
    db.commit()
    db.refresh(task)
    
    return TaskResponse(
        id=task.id,
        kindergarten_id=task.kindergarten_id,
        title=task.title,
        description=task.description,
        status=task.status.value,
        priority=task.priority.value,
        assigned_to=task.assigned_to,
        created_by=task.created_by,
        due_date=task.due_date,
        completed_at=task.completed_at,
        created_at=task.created_at
    )


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a task"""
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Check access - only creator or admin can delete
    if current_user.role != models.UserRole.ADMIN:
        if task.created_by != current_user.id:
            raise HTTPException(status_code=403, detail="Only task creator or admin can delete")
    
    db.delete(task)
    db.commit()
    
    return None
