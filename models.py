from sqlalchemy import DateTime, Float, ForeignKey, String, Boolean, Integer, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base
from datetime import UTC, datetime


class Users(Base):
    __tablename__ = "users"
    user_id: Mapped[str] = mapped_column(String(20), index=True, primary_key=True)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(30), nullable=False)
    address: Mapped[str] = mapped_column(String(100), nullable=False)
    phone_no: Mapped[str] = mapped_column(String(15), unique=True, nullable=False)
    consumer_no: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    distributor_name: Mapped[str] = mapped_column(ForeignKey("distributor.id"), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    district: Mapped[str] = mapped_column(String(20), nullable=False)
    device_id: Mapped[str | None] = mapped_column(String(30), unique=True, nullable=True, index=True)
    gas: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    threshold_limit: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    auto_delivery: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    sensor_readings: Mapped[list['Sensor_unit']] = relationship(back_populates='user')
    alerts: Mapped[list['Alert_log']] = relationship(back_populates='user')
    refill_requests: Mapped[list['Refill_request']] = relationship(back_populates='user')
    distributor: Mapped['Distributor'] = relationship(back_populates='users')


class Distributor(Base):
    __tablename__ = "distributor"
    id: Mapped[str] = mapped_column(String(20), index=True, primary_key=True)
    name: Mapped[str] = mapped_column(String(30), nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(String(100), nullable=False)
    phone_no: Mapped[str] = mapped_column(String(15), unique=True, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    district: Mapped[str] = mapped_column(String(20), nullable=False)
    
    users: Mapped[list['Users']] = relationship(back_populates='distributor')
    approved_refills: Mapped[list['Refill_request']] = relationship(back_populates='distributor')


class Admin(Base):
    __tablename__ = 'admin'
    id: Mapped[str] = mapped_column(String(20), index=True, primary_key=True)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(30), nullable=False)
    phone_no: Mapped[str] = mapped_column(String(15), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class DistributorRequest(Base):
    """Track requests from potential distributors for account creation."""
    __tablename__ = 'distributor_request'
    request_id: Mapped[str] = mapped_column(String(20), primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    phone_no: Mapped[str] = mapped_column(String(15), nullable=False)
    company_name: Mapped[str] = mapped_column(String(100), nullable=False)
    address: Mapped[str] = mapped_column(String(150), nullable=False)
    state: Mapped[str] = mapped_column(String(30), nullable=False)
    district: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default='pending', nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(20), nullable=True)
    review_comment: Mapped[str | None] = mapped_column(String(200), nullable=True)


class Alert_log(Base):
    __tablename__ = "alert_log"
    alert_id: Mapped[str] = mapped_column(String(30), index=True, primary_key=True)
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    delivery_status: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    time_stamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    
    user: Mapped['Users'] = relationship(back_populates='alerts')


class Sensor_unit(Base):
    __tablename__ = "sensor_unit"
    sensor_id: Mapped[str] = mapped_column(String(30), primary_key=True, index=True)
    current_weight: Mapped[float] = mapped_column(Float, nullable=False)
    connection_status: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.user_id'), nullable=False, index=True)
    
    user: Mapped['Users'] = relationship(back_populates='sensor_readings')
    __table_args__ = (Index('ix_sensor_device_time', 'user_id', 'timestamp'),)


class Refill_request(Base):
    __tablename__ = "refill_request"
    request_id: Mapped[str] = mapped_column(String(20), primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.user_id'), nullable=False, index=True)
    requested_status: Mapped[str] = mapped_column(String(15), nullable=False, default='pending')
    requested_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    approved_by: Mapped[str | None] = mapped_column(ForeignKey('distributor.id'), nullable=True)
    approved_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    user: Mapped['Users'] = relationship(back_populates='refill_requests')
    distributor: Mapped['Distributor | None'] = relationship(back_populates='approved_refills')


class Complaint(Base):
    """Customer complaints/support tickets."""
    __tablename__ = "complaint"
    complaint_id: Mapped[str] = mapped_column(String(20), primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.user_id'), nullable=False, index=True)
    distributor_id: Mapped[str] = mapped_column(ForeignKey('distributor.id'), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='Open')
    remark: Mapped[str] = mapped_column(String(500), nullable=True, default='')
    consumer_name: Mapped[str] = mapped_column(String(100), nullable=False)
    consumer_email: Mapped[str] = mapped_column(String(120), nullable=False)
    consumer_phone: Mapped[str] = mapped_column(String(15), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    user: Mapped['Users'] = relationship()
    distributor: Mapped['Distributor'] = relationship()


# ============================================================================
# SYNTHETIC DATA & ML FEATURE TABLES
# ============================================================================

class Synthetic_device(Base):
    """Metadata for synthetic devices used in model training."""
    __tablename__ = "synthetic_device"
    device_id: Mapped[str] = mapped_column(String(30), primary_key=True, index=True)
    dataset_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    lifecycle_count: Mapped[int] = mapped_column(Integer, nullable=False)  # Number of refill cycles
    
    readings: Mapped[list['Synthetic_sensor_reading']] = relationship(back_populates='device')
    features: Mapped[list['Synthetic_feature_row']] = relationship(back_populates='device')


class Synthetic_sensor_reading(Base):
    """Raw synthetic sensor readings for model training."""
    __tablename__ = "synthetic_sensor_reading"
    reading_id: Mapped[str] = mapped_column(String(30), primary_key=True, index=True)
    device_id: Mapped[str] = mapped_column(ForeignKey('synthetic_device.device_id'), nullable=False, index=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    is_refill: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    device: Mapped['Synthetic_device'] = relationship(back_populates='readings')
    __table_args__ = (Index('ix_synthetic_device_time', 'device_id', 'timestamp'),)


class Synthetic_feature_row(Base):
    """Computed features for synthetic readings (25+ features)."""
    __tablename__ = "synthetic_feature_row"
    feature_id: Mapped[str] = mapped_column(String(30), primary_key=True, index=True)
    device_id: Mapped[str] = mapped_column(ForeignKey('synthetic_device.device_id'), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    
    # Core delta/rate features
    weight: Mapped[float] = mapped_column(Float, nullable=True)
    prev_weight: Mapped[float] = mapped_column(Float, nullable=True)
    weight_delta: Mapped[float] = mapped_column(Float, nullable=True)
    time_gap_hours: Mapped[float] = mapped_column(Float, nullable=True)
    consumption_per_hour: Mapped[float] = mapped_column(Float, nullable=True)
    consumption_per_day: Mapped[float] = mapped_column(Float, nullable=True)
    
    # Time features
    hour_of_day: Mapped[int] = mapped_column(Integer, nullable=True)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=True)
    is_weekend: Mapped[bool] = mapped_column(Boolean, nullable=True)
    
    # Refill and lifecycle features
    is_refill: Mapped[bool] = mapped_column(Boolean, nullable=True)
    days_since_refill: Mapped[float] = mapped_column(Float, nullable=True)
    
    # Rolling/window features
    rolling_mean_1h: Mapped[float] = mapped_column(Float, nullable=True)
    rolling_mean_24h: Mapped[float] = mapped_column(Float, nullable=True)
    rolling_std_1h: Mapped[float] = mapped_column(Float, nullable=True)
    rolling_std_24h: Mapped[float] = mapped_column(Float, nullable=True)
    rolling_7day_avg_consumption: Mapped[float] = mapped_column(Float, nullable=True)
    rolling_30day_avg_consumption: Mapped[float] = mapped_column(Float, nullable=True)
    rolling_max_drop_1h: Mapped[float] = mapped_column(Float, nullable=True)
    
    # Session and usage features
    session_count_today: Mapped[int] = mapped_column(Integer, nullable=True)
    idle_drop_rate: Mapped[float] = mapped_column(Float, nullable=True)
    
    device: Mapped['Synthetic_device'] = relationship(back_populates='features')
    __table_args__ = (Index('ix_synthetic_feature_device_time', 'device_id', 'timestamp'),)


class Device_cluster_assignment(Base):
    """Stores device-to-cluster assignments from usage pattern clustering."""
    __tablename__ = "device_cluster_assignment"
    assignment_id: Mapped[str] = mapped_column(String(30), primary_key=True, index=True)
    device_id: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    cluster_id: Mapped[int] = mapped_column(Integer, nullable=False)
    model_version: Mapped[int] = mapped_column(Integer, nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    
    # Device characteristics (used for clustering decision)
    avg_daily_consumption: Mapped[float] = mapped_column(Float, nullable=True)
    peak_hour: Mapped[int] = mapped_column(Integer, nullable=True)
    weekend_multiplier: Mapped[float] = mapped_column(Float, nullable=True)
    session_count_per_day: Mapped[float] = mapped_column(Float, nullable=True)
    cylinder_lifetime_days: Mapped[float] = mapped_column(Float, nullable=True)
    
    # Confidence/metadata
    confidence_score: Mapped[float] = mapped_column(Float, nullable=True)


class Clustering_model_metadata(Base):
    """Tracks clustering model versions and performance."""
    __tablename__ = "clustering_model_metadata"
    model_id: Mapped[str] = mapped_column(String(30), primary_key=True, index=True)
    model_version: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    optimal_k: Mapped[int] = mapped_column(Integer, nullable=False)
    inertias: Mapped[list] = mapped_column(JSON, nullable=True)  # Inertia values for each k tested
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    training_records_count: Mapped[int] = mapped_column(Integer, nullable=True)
    model_path: Mapped[str] = mapped_column(String(255), nullable=True)
    scaler_path: Mapped[str] = mapped_column(String(255), nullable=True)


class Depletion_prediction_metadata(Base):
    """Tracks depletion prediction model versions and performance."""
    __tablename__ = "depletion_prediction_metadata"
    model_id: Mapped[str] = mapped_column(String(30), primary_key=True, index=True)
    model_version: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    model_type: Mapped[str] = mapped_column(String(20), nullable=False)  # 'rule_based' or 'linear_regression'
    mae_days: Mapped[float] = mapped_column(Float, nullable=True)
    rows_used: Mapped[int] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    model_path: Mapped[str] = mapped_column(String(255), nullable=True)

