from app import create_app
from app.database import db
from app.models import (
    ClassModel, 
    SectionModel, 
    SubjectModel, 
    TeacherModel, 
    StudentModel, 
    TestTypeModel  # Make sure this model is imported
)
from datetime import datetime

app = create_app()

def seed_database():
    with app.app_context():
        print("🌱 Clearing and resetting database...")
        db.drop_all()
        db.create_all()

        print("📚 Creating Classes, Sections, and Subjects...")
        class_names = [
            "Playgroup", "Nursery", "Class 1", "Class 2", "Class 3", 
            "Class 4", "Class 5", "Class 6", "Class 7", "Class 8", "Class 9", "Class 10"
        ]
        
        default_subjects = ["English", "Urdu", "Mathematics", "Islamiyat"]
        
        created_classes = {}
        for c_name in class_names:
            c_obj = ClassModel(name=c_name)
            db.session.add(c_obj)
            db.session.commit()
            created_classes[c_name] = c_obj

            # Add default sections A and B
            for s_name in ["A", "B"]:
                sec = SectionModel(name=s_name, class_id=c_obj.id)
                db.session.add(sec)
            
            # Add default subjects for each class
            for sub_name in default_subjects:
                sub = SubjectModel(name=sub_name, class_id=c_obj.id)
                db.session.add(sub)
        
        db.session.commit()

        print("🏷️ Seeding Test Types...")
        default_types = ["Daily", "Weekly", "15 Days", "Monthly", "3 Months", "6 Months", "9 Months", "1 Year"]
        for t_name in default_types:
            if not TestTypeModel.query.filter_by(name=t_name).first():
                db.session.add(TestTypeModel(name=t_name))
        db.session.commit()

        print("👨‍🏫 Creating Teachers...")
        teachers_data = [
            ("T001", "M. Akram", "M.Sc Mathematics", 45000, "Class 10"),
            ("T002", "Ayesha Bibi", "M.A English", 40000, "Class 9"),
            ("T003", "Tariq Mahmood", "B.Ed", 35000, "Class 5"),
            ("T004", "Fatima Noor", "ADC", 30000, "Playgroup")
        ]
        for t_id, t_name, qual, sal, cls in teachers_data:
            teacher = TeacherModel(
                teacher_id_str=t_id,
                teacher_name=t_name,
                joining_date=datetime.strptime("2023-01-15", "%Y-%m-%d"),
                qualification=qual,
                salary=sal,
                assigned_class=cls
            )
            db.session.add(teacher)
        db.session.commit()

        print("🎓 Generating 60 Dummy Students...")
        all_classes = ClassModel.query.all()
        
        student_count = 0
        first_names = ["Ali", "Ahmed", "Hassan", "Hussain", "Bilal", "Usman", "Zain", "Hamza", "Ayesha", "Fatima", "Zainab", "Maryam", "Khadija", "Esha", "Sana"]
        last_names = ["Khan", "Awan", "Baloch", "Malik", "Rana", "Sheikh", "Butt", "Gondal", "Qureshi", "Abbasi"]
        
        while student_count < 60:
            target_class = all_classes[student_count % len(all_classes)]
            sections = SectionModel.query.filter_by(class_id=target_class.id).all()
            target_section = sections[student_count % len(sections)] if sections else None

            f_name = first_names[student_count % len(first_names)]
            l_name = last_names[(student_count * 3) % len(last_names)]
            full_name = f"{f_name} {l_name}"
            father_name = f"Father of {f_name}"
            
            roll_no = f"RN-{1000 + student_count + 1}"
            phone = f"+923{str(300 + student_count % 900).zfill(3)}{str(1234567 + student_count)[-7:]}"
            
            student = StudentModel(
                roll_number=roll_no,
                student_name=full_name,
                father_name=father_name,
                guardian_phone=phone,
                address="Main Bazaar, Dera Ghazi Khan",
                class_id=target_class.id,
                section_id=target_section.id if target_section else None
            )
            db.session.add(student)
            student_count += 1

        db.session.commit()
        print("✅ Success! Database seeded with classes, sections, subjects, test types, teachers, and 60 students.")

if __name__ == '__main__':
    seed_database()