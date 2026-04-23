from ext import db
from app import create_app

app = create_app()
with app.app_context():
    # Add invoice_number to sales if missing
    try:
        db.engine.execute('ALTER TABLE sales ADD COLUMN invoice_number VARCHAR(50)')
        print("Added invoice_number to sales")
    except:
        pass
    
    # Add vendor_id to purchase if missing
    try:
        db.engine.execute('ALTER TABLE purchase ADD COLUMN vendor_id INTEGER REFERENCES vendor(id)')
        print("Added vendor_id to purchase")
    except Exception as e:
        print(f"vendor_id: {e}")
    
    # Create vendor table
    try:
        db.engine.execute('''
            CREATE TABLE IF NOT EXISTS vendor (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                phone VARCHAR(20),
                address TEXT,
                gstin VARCHAR(20),
                state VARCHAR(50),
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP
            )
        ''')
        print("Created vendor table")
    except Exception as e:
        print(f"vendor table: {e}")
    
    print("Done!")