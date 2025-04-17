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
    MIN_OVERLAP_PERCENT = 0.10  # Minimum 10% overlap to consider it a match
    
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
                    "x_center": (time_slot_numbers[i]["x0"] + time_slot_times[i]["x1_cell"]) / 2,  # Column center
                    "data": []
                })
        
        print("\n--- Defined Columns ---")  # Debugging
        for i, col in enumerate(columns):
            print(f"  Column {i + 1}: x0={col['x0']}, x1={col['x1']}, center={col['x_center']}")
        
        # --- 5. Analyze Rows and Extract Data ---
        for i, row in enumerate(rows):
            if i < 4:  # Skip the time slot definition rows
                continue
            
            print(f"\n--- Row {i + 1} ---")  # Debugging
            row_day = None
            min_x0 = min(cell["x0"] for cell in row) if row else float('inf')  # Find leftmost x0 (or infinity if row is empty)
            
            for cell in row:
                text = cell["text"]
                x0_cell = cell["x0"]
                x1_cell = cell["x1_cell"]
                cell_center = (x0_cell + x1_cell) / 2
                cell_width = x1_cell - x0_cell
                
                print(f"  Original Cell Text: '{text}'")  # Debugging
                
                # Check for Day (Robust)
                for day in days:
                    if abs((x0_cell + x1_cell) / 2 - day["x_center"]) <= DAY_X_TOLERANCE and x0_cell <= days[0]["x_center"]:
                        row_day = day["text"]
                        break
                if not row_day:
                    for day in days:
                        if x0_cell == min_x0 and text in ["Mo", "Tu", "We", "Th", "Fr", "Sa"]:
                            row_day = text
                            break
                
                if row_day and cell["text"] not in ["Mo", "Tu", "We", "Th", "Fr", "Sa"] and len(cell["text"]) > 1:
                    # Find the column for this cell
                    assigned = False
                    for j, col in enumerate(columns):
                        # Check for overlap with tolerance
                        overlap = max(0, min(x1_cell, col["x1"]) - max(x0_cell, col["x0"]))
                        overlap_percent = overlap / cell_width if cell_width > 0 else 0
                        center_distance = abs(cell_center - col["x_center"])
                        
                        print(f"    Column {j + 1}: overlap={overlap}, overlap_percent={overlap_percent:.2f}, center_distance={center_distance:.2f}")  # Debug
                        
                        if overlap_percent >= MIN_OVERLAP_PERCENT:
                            columns[j]["data"].append(cell["text"])
                            assigned = True
                            break
                    
                    if not assigned:
                        # If no significant overlap, check center distance
                        for j, col in enumerate(columns):
                            if center_distance <= COLUMN_TOLERANCE * 5:  # Wider tolerance for center
                                columns[j]["data"].append(cell["text"])
                                assigned = True
                                break
                        if not assigned:
                            print(f"  Warning: Cell '{text}' not assigned to any column.")  # Debugging
            
            print("  Columns Data:", [col["data"] for col in columns])  # Debugging
        
        # --- 6. Organize Extracted Data ---
        for j, col in enumerate(columns):
            time_slot = time_slots[j]["text"] if j < len(time_slots) else f"Unknown Time Slot {j + 1}"
            for original_text in col["data"]:  # Use original text
                # Enhanced Filtering (Regex)
                text = re.sub(r'\s+', ' ', original_text)  # Remove extra spaces
                text = re.sub(r'[^\x20-\x7F]+', '', text)  # Remove non-ASCII
                text = re.sub(r'[\x00-\x1F\x7F]', '', text)  # Remove control chars
                
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
                    "raw_text": original_text  # Store original
                })
        
    return section, data

if __name__ == '__main__':
    pdf_path = "CSE 1st Year Section Wise.pdf"
    section, timetable_data = extract_timetable_data(pdf_path, "BE-CSE-2A")
    print("Section:", section)
    print("--- Extracted Data ---")
    for entry in timetable_data:
        print(entry)
