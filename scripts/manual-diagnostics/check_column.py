from sqlalchemy import create_engine, inspect

engine = create_engine('sqlite:///kinjo_dev.db')
inspector = inspect(engine)
columns = inspector.get_columns('kindergartens')
email_col = [c for c in columns if c['name'] == 'contact_email'][0]
print(f"contact_email nullable: {email_col['nullable']}")
