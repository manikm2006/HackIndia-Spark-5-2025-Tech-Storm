from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer, LTTextBox, LTLine
import re
import datetime
import os
import numpy as np  # For clustering

def clean_text(text):
    """Cleans up extracted text by removing extra spaces and newlines."""
    return " ".join(text.split()).strip()

def is_time_slot(text):
    """Checks if the text matches the time slot pattern."""
    return re.match(r'\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}', text)

def cluster_y_coords(coords, tolerance):
    """Clusters Y coordinates to identify rows."""
    coords = np.array(coords)
    clusters = []
    while len(coords) > 0:
        cluster = [coords[0]]
        coords = np.delete(coords, 0)
        
        diffs = np.abs(coords - cluster[0])
        within_tolerance = np.where(diffs <= tolerance)[0]
        
        cluster.extend(coords[within_tolerance].tolist())
        coords = np.delete(coords, within_tolerance)
        
        clusters.append(np.mean(cluster))  # Use mean Y as row Y
    return clusters

def extract_timetable_data(pdf_path, target_section="BE-CSE-2A"):
    data = []
    section = None
    time_slots = []
    days = []
    rows = []
    
    # --- Thresholds (These are CRITICAL and need tuning) ---
    TIME_SLOT_Y_RANGE = (40, 60)
    DAY_Y_RANGE = (60, 80)
    DATA_START_Y = 80
    ROW_TOLERANCE = 5
    DAY_X_TOLERANCE = 10
    COLUMN_TOLERANCE = 3  # Allow slight variation in X-coordinates
    
    for page_layout in extract_pages(pdf_path):
        text_elements = [(clean_text(e.get_text()), e.bbox) for e in page_layout if isinstance(e, LTTextContainer)]
        
        # --- 1. Section ---
        for text, bbox in text_elements:
            if re.match(rf"{target_section}", text):
                section = text
                break
        
        if not section:
            continue
        
        # --- 2. Extract Time Slots and Days ---
        y_coords = []
        for text, (x0, y0, x1, y1) in text_elements:
            y_center = (y0 + y1) / 2
            
            if TIME_SLOT_Y_RANGE[0] <= y_center <= TIME_SLOT_Y_RANGE[1] and is_time_slot(text):
                time_slots.append({"text": text, "x0": x0, "x1": x1, "x_center": (x0 + x1) / 2})  # Store x_center
            elif DAY_Y_RANGE[0] <= y_center <= DAY_Y_RANGE[1] and text in ["Mo", "Tu", "We", "Th", "Fr", "Sa"]:
                days.append({"text": text, "x_center": (x0 + x1) / 2, "text": text})
            
            if y_center > DATA_START_Y:
                y_coords.append(y_center)
        
        # Sort time slots and days
        time_slots.sort(key=lambda x: x["x0"])
        days.sort(key=lambda x: x["x_center"])
        
        # --- 3. Group Elements into Rows (Y-Coordinate Clustering) ---
        row_y_coords = cluster_y_coords(y_coords, ROW_TOLERANCE)
        rows = [[] for _ in range(len(row_y_coords))]
        
        for text, (x0, y0, x1, y1) in text_elements:
            y_center = (y0 + y1) / 2
            if y_center > DATA_START_Y:
                for i, row_y in enumerate(row_y_coords):
                    if abs(y_center - row_y) <= ROW_TOLERANCE:
                        rows[i].append({"text": text, "x0": x0, "x1": x1, "y_center": y_center, "text": text, "x1_cell": x1})  # Keep text and x1
                        break
        
        # Sort elements within each row by x0
        for row in rows:
            row.sort(key=lambda x: x["x0"])
        
        # --- 4. Define Columns from Rows 3 and 4 ---
        columns = []
        if len(rows) >= 4:  # Make sure we have enough rows
            # Use data from row 3 and 4 to define columns
            time_slot_numbers = rows[2] if len(rows) > 2 else []
            time_slot_times = rows[3] if len(rows) > 3 else []
            
            for i in range(min(len(time_slot_numbers), len(time_slot_times))):
                columns.append({
                    "x0": time_slot_numbers[i]["x0"],
                    "x1": time_slot_times[i]["x1_cell"],  # Use x1 from time row
                    "data": []
                })
        
        print("\n--- Defined Columns ---")  # Debugging
        for i, col in enumerate(columns):
            print(f"  Column {i + 1}: x0={col['x0']}, x1={col['x1']}")
        
        # --- 5. Analyze Rows and Extract Data ---
        for i, row in enumerate(rows):
            if i < 4:  # Skip the time slot definition rows
                continue
            
            print(f"\n--- Row {i + 1} ---")  # Debugging
            row_day = None
            
            for cell in row:
                text = cell["text"]
                x0_cell = cell["x0"]
                x1_cell = cell["x1_cell"]
                
                # Check for Day
                for day in days:
                    if abs((x0_cell + x1_cell) / 2 - day["x_center"]) <= DAY_X_TOLERANCE:
                        row_day = day["text"]
                        break
                
                if row_day and cell["text"] not in ["Mo", "Tu", "We", "Th", "Fr", "Sa"] and len(cell["text"]) > 1:
                    # Find the column for this cell
                    assigned = False
                    for j, col in enumerate(columns):
                        # Check with tolerance
                        if col["x0"] - COLUMN_TOLERANCE <= x0_cell <= col["x1"] + COLUMN_TOLERANCE:
                            columns[j]["data"].append(cell["text"])
                            assigned = True
                            break
                    if not assigned:
                        print(f"  Warning: Cell '{text}' not assigned to any column.")  # Debugging
            
            print("  Columns Data:", [col["data"] for col in columns])  # Debugging
        
        # --- 6. Organize Extracted Data ---
        for j, col in enumerate(columns):
            time_slot = time_slots[j]["text"] if j < len(time_slots) else f"Unknown Time Slot {j + 1}"
            for text in col["data"]:
                # More robust noise filtering
                text = ''.join(filter(str.isalnum, text))
                if len(text) <= 2:
                    continue
                
                # Refined Regex
                subject_match = re.search(r'([A-Z]{2,}(?:-\w+)?)', text)
                subject = subject_match.group(1) if subject_match else None
                
                room_match = re.search(r'([A-Z]{2,3}\d+[A-Z]*)', text)
                room = room_match.group(1) if room_match else None
                
                group_match = re.search(r'(Group\s*\d+)', text)
                group = group_match.group(1) if group_match else None
                
                data.append({
                    "day": row_day,
                    "time": time_slot,
                    "subject": subject,
                    "room": room,
                    "group": group,
                    "raw_text": text
                })
        
    return section, data

if __name__ == '__main__':
    pdf_path = "CSE 1st Year Section Wise.pdf"
    section, timetable_data = extract_timetable_data(pdf_path, "BE-CSE-2A")
    print("Section:", section)
    print("--- Extracted Data ---")
    for entry in timetable_data:
        print(entry)
