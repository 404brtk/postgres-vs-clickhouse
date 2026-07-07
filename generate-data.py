import csv
import random
from datetime import datetime, timedelta

records = 25_000_000
print(f"Generating {records} events...")

start_date = datetime(2026, 1, 1)

with open('user_events.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['event_id', 'user_id', 'target_id', 'category_id', 'event_type', 'duration_sec', 'is_liked', 'event_time', 'device', 'commission'])
    
    for i in range(records):
        event_time = start_date + timedelta(seconds=random.randint(0, 15552000))
        event_type = random.choice(['view', 'click', 'scroll', 'share'])
        
        if event_type == 'click':
            commission = round(random.uniform(0.05, 2.50), 2)
        elif event_type == 'share':
            commission = round(random.uniform(0.50, 5.00), 2)
        else:
            commission = 0.00
            
        device = random.choice(['mobile', 'desktop', 'tablet'])
        
        writer.writerow([
            i,
            random.randint(1, 100000),
            random.randint(1, 50000),
            random.randint(1, 20),
            event_type,
            random.randint(2, 600),
            random.choice([0, 0, 0, 1]),
            event_time.strftime('%Y-%m-%d %H:%M:%S'),
            device,
            commission
        ])
        if i % 5_000_000 == 0 and i > 0:
            print(f"Generated {i}... ")

print("Done! File user_events.csv created.")