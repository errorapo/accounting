from ext import db
from app import create_app

app = create_app()
with app.app_context():
    db.engine.execute('ALTER TABLE user ADD COLUMN role VARCHAR(20) DEFAULT "accountant"')
    print("Done!")