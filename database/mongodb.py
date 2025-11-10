# database/mongodb.py - MongoDB operations
import os
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class MongoDB:
    def __init__(self):
        self.client = None
        self.db = None
    
    async def connect(self):
        """Connect to MongoDB"""
        try:
            self.client = AsyncIOMotorClient(os.getenv("MONGODB_URI"))
            self.db = self.client[os.getenv("DB_NAME", "remedi_chronic_care")]
            
            # Create indexes
            await self._create_indexes()
            
            logger.info("MongoDB connected successfully")
        except Exception as e:
            logger.error(f"MongoDB connection error: {str(e)}")
            raise
    
    async def disconnect(self):
        """Disconnect from MongoDB"""
        if self.client:
            self.client.close()
            logger.info("MongoDB disconnected")
    
    async def _create_indexes(self):
        """Create database indexes"""
        # Patients collection indexes
        await self.db.patients.create_index("whatsapp_number", unique=True)
        await self.db.patients.create_index("patient_id", unique=True)
        await self.db.patients.create_index("approval_status")
        
        # Reports collection indexes
        await self.db.reports.create_index("patient_id")
        await self.db.reports.create_index("upload_date")
        
        # BP readings collection indexes
        await self.db.bp_readings.create_index([("patient_id", 1), ("reading_date", -1)])
        
        # Appointments collection indexes
        await self.db.appointments.create_index([("patient_id", 1), ("scheduled_date", 1)])
        await self.db.appointments.create_index("status")
    
    # ==================== PATIENT OPERATIONS ====================
    
    async def get_patient_by_phone(self, phone):
        """Get patient by WhatsApp number"""
        return await self.db.patients.find_one({"whatsapp_number": phone})
    
    async def get_patient_by_id(self, patient_id):
        """Get patient by patient ID"""
        return await self.db.patients.find_one({"patient_id": patient_id})
    
    async def create_patient(self, patient_data):
        """Create new patient"""
        # Generate patient ID
        patient_id = await self._generate_patient_id()
        patient_data["patient_id"] = patient_id
        patient_data["enrollment_date"] = datetime.utcnow()
        patient_data["created_at"] = datetime.utcnow()
        
        result = await self.db.patients.insert_one(patient_data)
        return patient_id
    
    async def update_patient(self, patient_id, update_data):
        """Update patient data"""
        update_data["updated_at"] = datetime.utcnow()
        
        await self.db.patients.update_one(
            {"patient_id": patient_id},
            {"$set": update_data}
        )
    
    async def update_patient_conversation_state(self, patient_id, state):
        """Update patient conversation state"""
        await self.db.patients.update_one(
            {"patient_id": patient_id},
            {"$set": {
                "conversation_state": state,
                "last_interaction": datetime.utcnow()
            }}
        )
    
    async def increment_patient_stat(self, patient_id, stat_name):
        """Increment a patient statistic"""
        await self.db.patients.update_one(
            {"patient_id": patient_id},
            {"$inc": {stat_name: 1}}
        )
    
    async def _generate_patient_id(self):
        """Generate unique patient ID in format RMD-YY-XXX"""
        year = datetime.utcnow().strftime("%y")
        prefix = f"RMD-{year}-"
        
        # Find latest patient for this year
        latest = await self.db.patients.find_one(
            {"patient_id": {"$regex": f"^{prefix}"}},
            sort=[("patient_id", -1)]
        )
        
        if latest:
            last_num = int(latest["patient_id"].split("-")[2])
            next_num = last_num + 1
        else:
            next_num = 1
        
        return f"{prefix}{next_num:03d}"
    
    # ==================== BLOOD TEST OPERATIONS ====================
    
    async def schedule_blood_tests(self, patient_id):
        """Schedule blood tests based on patient conditions"""
        patient = await self.get_patient_by_id(patient_id)
        conditions = patient.get("health_conditions", [])
        
        tests = []
        base_date = datetime.utcnow()
        
        for condition in conditions:
            if condition == "Diabetes":
                # Quarterly
                tests.extend([
                    {
                        "test_name": "HbA1c",
                        "due_date": base_date + timedelta(days=90),
                        "frequency": "quarterly",
                        "condition": "Diabetes",
                        "completed": False
                    },
                    {
                        "test_name": "Fasting Glucose",
                        "due_date": base_date + timedelta(days=90),
                        "frequency": "quarterly",
                        "condition": "Diabetes",
                        "completed": False
                    }
                ])
                # Annual
                tests.extend([
                    {
                        "test_name": "Lipid Panel",
                        "due_date": base_date + timedelta(days=365),
                        "frequency": "annual",
                        "condition": "Diabetes",
                        "completed": False
                    },
                    {
                        "test_name": "Kidney Function",
                        "due_date": base_date + timedelta(days=365),
                        "frequency": "annual",
                        "condition": "Diabetes",
                        "completed": False
                    }
                ])
            
            elif condition == "Hypertension":
                # Semi-annual
                tests.append({
                    "test_name": "Blood Pressure Monitoring",
                    "due_date": base_date + timedelta(days=180),
                    "frequency": "semi-annual",
                    "condition": "Hypertension",
                    "completed": False
                })
                # Annual
                tests.extend([
                    {
                        "test_name": "Lipid Panel",
                        "due_date": base_date + timedelta(days=365),
                        "frequency": "annual",
                        "condition": "Hypertension",
                        "completed": False
                    },
                    {
                        "test_name": "ECG",
                        "due_date": base_date + timedelta(days=365),
                        "frequency": "annual",
                        "condition": "Hypertension",
                        "completed": False
                    }
                ])
            
            elif condition == "High Cholesterol":
                tests.extend([
                    {
                        "test_name": "Lipid Panel",
                        "due_date": base_date + timedelta(days=180),
                        "frequency": "semi-annual",
                        "condition": "High Cholesterol",
                        "completed": False
                    },
                    {
                        "test_name": "Liver Function",
                        "due_date": base_date + timedelta(days=365),
                        "frequency": "annual",
                        "condition": "High Cholesterol",
                        "completed": False
                    }
                ])
            
            elif condition == "Kidney Disease":
                tests.extend([
                    {
                        "test_name": "Creatinine",
                        "due_date": base_date + timedelta(days=90),
                        "frequency": "quarterly",
                        "condition": "Kidney Disease",
                        "completed": False
                    },
                    {
                        "test_name": "eGFR",
                        "due_date": base_date + timedelta(days=90),
                        "frequency": "quarterly",
                        "condition": "Kidney Disease",
                        "completed": False
                    }
                ])
            
            elif condition == "Thyroid Disorder":
                tests.extend([
                    {
                        "test_name": "TSH",
                        "due_date": base_date + timedelta(days=180),
                        "frequency": "semi-annual",
                        "condition": "Thyroid Disorder",
                        "completed": False
                    },
                    {
                        "test_name": "Free T4",
                        "due_date": base_date + timedelta(days=180),
                        "frequency": "semi-annual",
                        "condition": "Thyroid Disorder",
                        "completed": False
                    }
                ])
        
        await self.update_patient(patient_id, {"next_blood_tests": tests})
    
    async def get_due_blood_tests(self, days_ahead=7):
        """Get tests due in the next N days"""
        cutoff_date = datetime.utcnow() + timedelta(days=days_ahead)
        
        pipeline = [
            {"$unwind": "$next_blood_tests"},
            {
                "$match": {
                    "next_blood_tests.due_date": {"$lte": cutoff_date},
                    "next_blood_tests.completed": False,
                    "approval_status": "approved"
                }
            }
        ]
        
        cursor = self.db.patients.aggregate(pipeline)
        return await cursor.to_list(length=None)
    
    # ==================== REPORT OPERATIONS ====================
    
    async def save_report(self, report_data):
        """Save lab report"""
        report_data["created_at"] = datetime.utcnow()
        result = await self.db.reports.insert_one(report_data)
        return report_data["report_id"]
    
    async def get_patient_reports(self, patient_id, limit=10):
        """Get patient's recent reports"""
        cursor = self.db.reports.find(
            {"patient_id": patient_id}
        ).sort("upload_date", -1).limit(limit)
        
        return await cursor.to_list(length=limit)
    
    # ==================== BP READING OPERATIONS ====================
    
    async def save_bp_reading(self, reading_data):
        """Save BP reading"""
        reading_data["created_at"] = datetime.utcnow()
        result = await self.db.bp_readings.insert_one(reading_data)
        return str(result.inserted_id)
    
    async def get_recent_bp_readings(self, patient_id, limit=None, days=None):
        """Get recent BP readings"""
        query = {"patient_id": patient_id}
        
        if days:
            cutoff = datetime.utcnow() - timedelta(days=days)
            query["reading_date"] = {"$gte": cutoff}
        
        cursor = self.db.bp_readings.find(query).sort("reading_date", -1)
        
        if limit:
            cursor = cursor.limit(limit)
        
        return await cursor.to_list(length=limit or 100)
    
    async def get_bp_average(self, patient_id, days=7):
        """Get average BP for last N days"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        pipeline = [
            {
                "$match": {
                    "patient_id": patient_id,
                    "reading_date": {"$gte": cutoff}
                }
            },
            {
                "$group": {
                    "_id": None,
                    "avg_systolic": {"$avg": "$systolic"},
                    "avg_diastolic": {"$avg": "$diastolic"}
                }
            }
        ]
        
        cursor = self.db.bp_readings.aggregate(pipeline)
        result = await cursor.to_list(length=1)
        
        if result:
            return {
                "systolic": round(result[0]["avg_systolic"]),
                "diastolic": round(result[0]["avg_diastolic"])
            }
        return {"systolic": 0, "diastolic": 0}
    
    # ==================== APPOINTMENT OPERATIONS ====================
    
    async def create_appointment(self, appointment_data):
        """Create new appointment"""
        appointment_data["created_at"] = datetime.utcnow()
        result = await self.db.appointments.insert_one(appointment_data)
        return appointment_data["appointment_id"]
    
    async def get_upcoming_appointments(self, hours_ahead=24):
        """Get appointments in next N hours"""
        start_time = datetime.utcnow()
        end_time = start_time + timedelta(hours=hours_ahead)
        
        cursor = self.db.appointments.find({
            "scheduled_date": {"$gte": start_time, "$lte": end_time},
            "status": {"$nin": ["completed", "cancelled"]}
        })
        
        return await cursor.to_list(length=None)
    
    async def update_appointment(self, appointment_id, update_data):
        """Update appointment"""
        await self.db.appointments.update_one(
            {"appointment_id": appointment_id},
            {"$set": update_data}
        )
    
    # ==================== ADMIN OPERATIONS ====================
    
    async def get_admin_stats(self):
        """Get admin dashboard statistics"""
        total_patients = await self.db.patients.count_documents({})
        active_patients = await self.db.patients.count_documents({"approval_status": "approved"})
        pending_approvals = await self.db.patients.count_documents({"approval_status": "pending"})
        
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        
        todays_appointments = await self.db.appointments.count_documents({
            "scheduled_date": {"$gte": today, "$lt": tomorrow}
        })
        
        todays_reports = await self.db.reports.count_documents({
            "upload_date": {"$gte": today}
        })
        
        critical_patients = await self.db.patients.count_documents({"is_high_risk": True})
        
        return {
            "total_patients": total_patients,
            "active_patients": active_patients,
            "pending_approvals": pending_approvals,
            "todays_appointments": todays_appointments,
            "todays_reports": todays_reports,
            "critical_patients": critical_patients,
            "timestamp": datetime.utcnow()
        }