"""Blog post CRUD + multi-image uploads."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlmodel import Session, delete, func, select

from app.database import get_session
from app.models import Post, PostImage, utcnow
from app.schemas import PostCreate, PostRead, PostUpdate, UploadResult
from app.storage import delete_stored, save_uploads

router = APIRouter(prefix="/api/posts", tags=["posts"])


def _get_or_404(session: Session, post_id: int) -> Post:
    post = session.get(Post, post_id)
    if post is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Post not found")
    return post


@router.get("", response_model=List[PostRead])
def list_posts(
    session: Session = Depends(get_session),
    q: Optional[str] = Query(default=None, description="Search title/content"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> List[Post]:
    stmt = select(Post)
    if q:
        needle = f"%{q.lower()}%"
        stmt = stmt.where(
            func.lower(Post.title).like(needle) | func.lower(Post.content).like(needle)
        )
    stmt = stmt.order_by(Post.created_at.desc(), Post.id.desc()).offset(offset).limit(limit)
    return list(session.exec(stmt).all())


@router.get("/{post_id}", response_model=PostRead)
def get_post(post_id: int, session: Session = Depends(get_session)) -> Post:
    return _get_or_404(session, post_id)


@router.post("", response_model=PostRead, status_code=status.HTTP_201_CREATED)
def create_post(payload: PostCreate, session: Session = Depends(get_session)) -> Post:
    post = Post(title=payload.title.strip(), content=payload.content)
    session.add(post)
    session.commit()
    session.refresh(post)
    return post


@router.patch("/{post_id}", response_model=PostRead)
def update_post(
    post_id: int, payload: PostUpdate, session: Session = Depends(get_session)
) -> Post:
    post = _get_or_404(session, post_id)
    data = payload.model_dump(exclude_unset=True)
    if "title" in data and data["title"] is not None:
        data["title"] = data["title"].strip()
    for key, value in data.items():
        setattr(post, key, value)
    post.updated_at = utcnow()
    session.add(post)
    session.commit()
    session.refresh(post)
    return post


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_post(post_id: int, session: Session = Depends(get_session)) -> None:
    post = _get_or_404(session, post_id)
    paths = [img.file_path for img in post.images]
    session.delete(post)
    session.commit()
    for path in paths:
        delete_stored(path)


@router.post("/{post_id}/images", response_model=UploadResult, status_code=status.HTTP_201_CREATED)
async def upload_post_images(
    post_id: int,
    files: List[UploadFile] = File(..., description="One or more image files"),
    session: Session = Depends(get_session),
) -> UploadResult:
    post = _get_or_404(session, post_id)
    urls = await save_uploads(files, f"posts/{post_id}")
    if not urls:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No image files received")

    images = [PostImage(post_id=post.id, file_path=url) for url in urls]
    session.add_all(images)
    post.updated_at = utcnow()
    session.add(post)
    session.commit()
    for img in images:
        session.refresh(img)
    return UploadResult(images=images)


@router.delete("/{post_id}/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_post_image(
    post_id: int, image_id: int, session: Session = Depends(get_session)
) -> None:
    image = session.get(PostImage, image_id)
    if image is None or image.post_id != post_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Image not found")
    path = image.file_path
    session.delete(image)
    session.commit()
    delete_stored(path)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def clear_posts(session: Session = Depends(get_session)) -> None:
    """Delete every post, its images, and the files on disk."""
    for path in session.exec(select(PostImage.file_path)).all():
        delete_stored(path)
    session.execute(delete(PostImage))
    session.execute(delete(Post))
    session.commit()
