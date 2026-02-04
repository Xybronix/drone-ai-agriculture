"""
History Routes.
Endpoints for retrieving analysis history.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_

from api.models import HistoryResponse, HistoryEntry, ErrorResponse
from api.database import get_session, Analysis, User
from api.config import get_settings
from api.routes.auth import get_optional_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/history", tags=["History"])
settings = get_settings()


@router.get(
    "",
    response_model=HistoryResponse,
    summary="Get analysis history",
    description="""
    Retrieve paginated analysis history with optional filters.

    **Filters:**
    - Date range (start_date, end_date)
    - Drone ID
    - Field ID
    - Species
    - Health status
    - Growth stage

    **Pagination:**
    - page: Page number (1-indexed)
    - page_size: Items per page (max 100)
    """
)
async def get_history(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    start_date: Optional[datetime] = Query(None, description="Start date filter"),
    end_date: Optional[datetime] = Query(None, description="End date filter"),
    drone_id: Optional[str] = Query(None, description="Filter by drone ID"),
    field_id: Optional[str] = Query(None, description="Filter by field ID"),
    species: Optional[str] = Query(None, description="Filter by species"),
    health_status: Optional[str] = Query(None, description="Filter by health status"),
    growth_stage: Optional[str] = Query(None, description="Filter by growth stage"),
    plant_detected: Optional[bool] = Query(None, description="Filter by plant detection"),
    session: AsyncSession = Depends(get_session),
    current_user: Optional[User] = Depends(get_optional_user)
):
    """Get paginated analysis history with optional filters."""
    from api.database import User
    
    # Build query
    query = select(Analysis)
    count_query = select(func.count(Analysis.id))

    # Apply filters
    filters = []

    # Filter by user - super admin sees all, regular users see only their own
    if current_user:
        if not current_user.is_super_admin:
            filters.append(Analysis.user_id == current_user.id)
    else:
        # Guest mode - return empty
        return HistoryResponse(
            total=0,
            page=page,
            page_size=page_size,
            entries=[]
        )

    if start_date:
        filters.append(Analysis.timestamp >= start_date)
    if end_date:
        filters.append(Analysis.timestamp <= end_date)
    if drone_id:
        filters.append(Analysis.drone_id == drone_id)
    if field_id:
        filters.append(Analysis.field_id == field_id)
    if species:
        filters.append(Analysis.species == species)
    if health_status:
        filters.append(Analysis.health_status == health_status)
    if growth_stage:
        filters.append(Analysis.growth_stage == growth_stage)
    if plant_detected is not None:
        filters.append(Analysis.plant_detected == plant_detected)

    if filters:
        query = query.where(and_(*filters))
        count_query = count_query.where(and_(*filters))

    # Get total count
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination and ordering
    offset = (page - 1) * page_size
    query = query.order_by(desc(Analysis.timestamp)).offset(offset).limit(page_size)

    # Execute query
    result = await session.execute(query)
    analyses = result.scalars().all()

    # Convert to response format
    entries = []
    for analysis in analyses:
        location = None
        if analysis.latitude and analysis.longitude:
            location = {
                "latitude": analysis.latitude,
                "longitude": analysis.longitude
            }

        entries.append(HistoryEntry(
            analysis_id=analysis.id,
            timestamp=analysis.timestamp,
            drone_id=analysis.drone_id,
            field_id=analysis.field_id,
            species=analysis.species,
            health_status=analysis.health_status,
            growth_stage=analysis.growth_stage,
            location=location,
            thumbnail_url=analysis.thumbnail_url
        ))

    return HistoryResponse(
        total=total,
        page=page,
        page_size=page_size,
        entries=entries
    )


@router.get(
    "/stats",
    summary="Get analysis statistics",
    description="Get aggregated statistics for analysis history"
)
async def get_stats(
    start_date: Optional[datetime] = Query(None, description="Start date"),
    end_date: Optional[datetime] = Query(None, description="End date"),
    field_id: Optional[str] = Query(None, description="Filter by field ID"),
    all_users: Optional[bool] = Query(False, description="Include all users' data (super admin only)"),
    session: AsyncSession = Depends(get_session),
    current_user: Optional[User] = Depends(get_optional_user)
):
    """
    Get aggregated statistics for analyses.
    Regular users see only their own data.
    Super admin can use all_users=true to see all users' data.
    """
    from api.database import User
    
    # Build base filter
    filters = []
    
    # Filter by user - super admin can see all if all_users=true, otherwise only their own
    if current_user:
        if not all_users or not current_user.is_super_admin:
            # Regular users or super admin viewing own data
            filters.append(Analysis.user_id == current_user.id)
        # If all_users=true and is_super_admin, no user filter (see all)
    else:
        # Guest mode - return empty stats
        return {
            "total_analyses": 0,
            "plants_detected": 0,
            "detection_rate": 0,
            "health_distribution": {},
            "species_distribution": {},
            "growth_stage_distribution": {},
            "avg_processing_time_ms": 0,
            "daily_analyses": []
        }
    
    if start_date:
        filters.append(Analysis.timestamp >= start_date)
    if end_date:
        filters.append(Analysis.timestamp <= end_date)
    if field_id:
        filters.append(Analysis.field_id == field_id)

    base_query = select(Analysis)
    if filters:
        base_query = base_query.where(and_(*filters))

    # Total analyses
    total_query = select(func.count(Analysis.id))
    if filters:
        total_query = total_query.where(and_(*filters))
    total_result = await session.execute(total_query)
    total_analyses = total_result.scalar() or 0

    # Plants detected
    plants_query = select(func.count(Analysis.id)).where(Analysis.plant_detected == True)
    if filters:
        plants_query = plants_query.where(and_(*filters))
    plants_result = await session.execute(plants_query)
    plants_detected = plants_result.scalar() or 0

    # Health status distribution
    health_query = select(
        Analysis.health_status,
        func.count(Analysis.id).label('count')
    ).group_by(Analysis.health_status)
    if filters:
        health_query = health_query.where(and_(*filters))
    health_result = await session.execute(health_query)
    health_distribution = {row[0]: row[1] for row in health_result.all() if row[0]}

    # Species distribution
    species_query = select(
        Analysis.species,
        func.count(Analysis.id).label('count')
    ).group_by(Analysis.species)
    if filters:
        species_query = species_query.where(and_(*filters))
    species_result = await session.execute(species_query)
    species_distribution = {row[0]: row[1] for row in species_result.all() if row[0]}

    # Growth stage distribution
    growth_query = select(
        Analysis.growth_stage,
        func.count(Analysis.id).label('count')
    ).group_by(Analysis.growth_stage)
    if filters:
        growth_query = growth_query.where(and_(*filters))
    growth_result = await session.execute(growth_query)
    growth_distribution = {row[0]: row[1] for row in growth_result.all() if row[0]}

    # Average processing time
    avg_time_query = select(func.avg(Analysis.processing_time_ms))
    if filters:
        avg_time_query = avg_time_query.where(and_(*filters))
    avg_time_result = await session.execute(avg_time_query)
    avg_processing_time = avg_time_result.scalar() or 0

    # Analyses per day (last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    daily_query = select(
        func.date(Analysis.timestamp).label('date'),
        func.count(Analysis.id).label('count')
    ).where(
        Analysis.timestamp >= thirty_days_ago
    ).group_by(
        func.date(Analysis.timestamp)
    ).order_by(
        func.date(Analysis.timestamp)
    )
    daily_result = await session.execute(daily_query)
    daily_analyses = [
        {"date": str(row[0]), "count": row[1]}
        for row in daily_result.all()
    ]

    return {
        "total_analyses": total_analyses,
        "plants_detected": plants_detected,
        "detection_rate": round(plants_detected / total_analyses * 100, 2) if total_analyses > 0 else 0,
        "health_distribution": health_distribution,
        "species_distribution": species_distribution,
        "growth_stage_distribution": growth_distribution,
        "avg_processing_time_ms": round(avg_processing_time, 2),
        "daily_analyses": daily_analyses
    }


@router.get(
    "/admin-stats",
    summary="Get admin statistics (super admin only)",
    description="Get global statistics for all users"
)
async def get_admin_stats(
    session: AsyncSession = Depends(get_session),
    current_user: Optional[User] = Depends(get_optional_user)
):
    """Get admin-level statistics. Super admin only."""
    if not current_user or not current_user.is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required"
        )
    
    from datetime import date
    
    # Total users
    users_result = await session.execute(select(func.count(User.id)))
    total_users = users_result.scalar() or 0
    
    # Total analyses
    analyses_result = await session.execute(select(func.count(Analysis.id)))
    total_analyses = analyses_result.scalar() or 0
    
    # Analyses today
    today = date.today()
    today_result = await session.execute(
        select(func.count(Analysis.id)).where(
            func.date(Analysis.timestamp) == today
        )
    )
    analyses_today = today_result.scalar() or 0
    
    # Top users by analysis count
    top_users_query = select(
        Analysis.user_id,
        Analysis.guest_identifier,
        func.count(Analysis.id).label('count'),
        func.max(Analysis.timestamp).label('last_activity')
    ).group_by(
        Analysis.user_id, Analysis.guest_identifier
    ).order_by(
        desc('count')
    ).limit(10)
    
    top_users_result = await session.execute(top_users_query)
    top_users_raw = top_users_result.all()
    
    top_users = []
    for row in top_users_raw:
        user_id, guest_id, count, last_activity = row
        
        username = None
        if user_id:
            user_result = await session.execute(
                select(User.username).where(User.id == user_id)
            )
            username = user_result.scalar()
        
        # Calculate healthy rate for this user
        healthy_query = select(func.count(Analysis.id)).where(
            Analysis.health_status.in_(['healthy', 'sain'])
        )
        if user_id:
            healthy_query = healthy_query.where(Analysis.user_id == user_id)
        elif guest_id:
            healthy_query = healthy_query.where(Analysis.guest_identifier == guest_id)
        
        healthy_result = await session.execute(healthy_query)
        healthy_count = healthy_result.scalar() or 0
        healthy_rate = round((healthy_count / count) * 100, 1) if count > 0 else 0
        
        top_users.append({
            "username": username,
            "guest_id": guest_id[:8] + "..." if guest_id else None,
            "is_guest": user_id is None,
            "analysis_count": count,
            "healthy_rate": healthy_rate,
            "last_activity": last_activity.isoformat() if last_activity else None
        })
    
    return {
        "total_users": total_users,
        "total_analyses": total_analyses,
        "analyses_today": analyses_today,
        "top_users": top_users
    }


@router.get(
    "/export",
    summary="Export analysis history",
    description="Export analysis history as JSON or CSV"
)
async def export_history(
    format: str = Query("json", pattern="^(json|csv)$", description="Export format"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    field_id: Optional[str] = Query(None),
    limit: int = Query(1000, le=10000, description="Maximum records to export"),
    session: AsyncSession = Depends(get_session)
):
    """
    Export analysis history in JSON or CSV format.
    """
    # Build query
    query = select(Analysis)
    filters = []

    if start_date:
        filters.append(Analysis.timestamp >= start_date)
    if end_date:
        filters.append(Analysis.timestamp <= end_date)
    if field_id:
        filters.append(Analysis.field_id == field_id)

    if filters:
        query = query.where(and_(*filters))

    query = query.order_by(desc(Analysis.timestamp)).limit(limit)

    result = await session.execute(query)
    analyses = result.scalars().all()

    if format == "csv":
        import csv
        from io import StringIO
        from fastapi.responses import StreamingResponse

        output = StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            "analysis_id", "timestamp", "drone_id", "field_id",
            "plant_detected", "species", "growth_stage", "health_status",
            "latitude", "longitude", "processing_time_ms"
        ])

        # Data
        for analysis in analyses:
            writer.writerow([
                analysis.id,
                analysis.timestamp.isoformat(),
                analysis.drone_id,
                analysis.field_id,
                analysis.plant_detected,
                analysis.species,
                analysis.growth_stage,
                analysis.health_status,
                analysis.latitude,
                analysis.longitude,
                analysis.processing_time_ms
            ])

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=analysis_history.csv"}
        )

    else:
        # JSON format
        data = []
        for analysis in analyses:
            data.append({
                "analysis_id": analysis.id,
                "timestamp": analysis.timestamp.isoformat(),
                "drone_id": analysis.drone_id,
                "field_id": analysis.field_id,
                "plant_detected": analysis.plant_detected,
                "species": analysis.species,
                "growth_stage": analysis.growth_stage,
                "health_status": analysis.health_status,
                "location": {
                    "latitude": analysis.latitude,
                    "longitude": analysis.longitude,
                    "altitude": analysis.altitude
                } if analysis.latitude else None,
                "processing_time_ms": analysis.processing_time_ms,
                "image_url": analysis.image_url
            })

        return {"count": len(data), "data": data}


@router.delete(
    "/{analysis_id}",
    summary="Delete an analysis",
    responses={404: {"model": ErrorResponse}}
)
async def delete_analysis(
    analysis_id: str,
    session: AsyncSession = Depends(get_session)
):
    """
    Delete a specific analysis by ID (GDPR compliance).
    """
    result = await session.execute(
        select(Analysis).where(Analysis.id == analysis_id)
    )
    analysis = result.scalar_one_or_none()

    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    await session.delete(analysis)
    await session.commit()

    logger.info(f"Analysis {analysis_id} deleted")

    return {"message": f"Analysis {analysis_id} deleted successfully"}


@router.delete(
    "",
    summary="Bulk delete analyses",
    description="Delete multiple analyses by IDs or date range"
)
async def bulk_delete(
    analysis_ids: Optional[List[str]] = Query(None, description="List of analysis IDs"),
    start_date: Optional[datetime] = Query(None, description="Delete from this date"),
    end_date: Optional[datetime] = Query(None, description="Delete until this date"),
    confirm: bool = Query(False, description="Confirm deletion"),
    session: AsyncSession = Depends(get_session)
):
    """
    Bulk delete analyses. Requires confirmation.
    """
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Please set confirm=true to proceed with deletion"
        )

    if not analysis_ids and not (start_date or end_date):
        raise HTTPException(
            status_code=400,
            detail="Please provide analysis_ids or date range"
        )

    from sqlalchemy import delete

    query = delete(Analysis)
    filters = []

    if analysis_ids:
        filters.append(Analysis.id.in_(analysis_ids))
    if start_date:
        filters.append(Analysis.timestamp >= start_date)
    if end_date:
        filters.append(Analysis.timestamp <= end_date)

    if filters:
        query = query.where(and_(*filters))

    result = await session.execute(query)
    await session.commit()

    deleted_count = result.rowcount

    logger.info(f"Bulk deleted {deleted_count} analyses")

    return {"message": f"Deleted {deleted_count} analyses"}