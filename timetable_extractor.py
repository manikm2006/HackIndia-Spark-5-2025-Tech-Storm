from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer, LTTextBox, LTLine
import re
import numpy as np

def clean_text(text):
    """
    Cleans extracted text by removing extra spaces and newlines, and stripping leading/trailing whitespace.

    Args:
        text (str): The text to clean.

    Returns:
        str: The cleaned text.
    """
    return " ".join(text.split()).strip()

def is_time_slot(text):
    """
    Checks if the text matches the time slot pattern (e.g., "10:00 - 11:00").

    Args:
        text (str): The text to check.

    Returns:
        bool: True if the text is a time slot, False otherwise.
    """
    return re.match(r'\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}', text)

def cluster_y_coords(coords, tolerance):
    """
    Clusters Y coordinates to identify rows, using a tolerance.  Averages the Y coords
    in each cluster to get the row Y coordinate.

    Args:
        coords (list): A list of Y coordinates.
        tolerance (float): The tolerance for clustering.

    Returns:
        list: A list of clustered Y coordinates (row Y values).
    """
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
    """
    Extracts timetable data from a PDF file for a specific section.

    Args:
        pdf_path (str): The path to the PDF file.
        target_section (str, optional): The section to extract data for. Defaults to "BE-CSE-2A".

    Returns:
        tuple: A tuple containing the section name (str) and the extracted timetable data (list of dicts).
               Returns (None, []) if the section is not found.  Each dictionary in the list
               represents a scheduled class and contains:
                   'day' (str): Day of the week.
                   'time' (str): Time slot.
                   'subject' (str): Subject name or code.
                   'room' (str): Room number.
                   'group' (str): Group information.
                   'raw_text' (str): The original extracted text.
    """
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
    DAY_X_TOLERANCE = 15  # Increased tolerance for day detection
    COLUMN_TOLERANCE = 10  # Increased tolerance for column assignment
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
                # Handle potential index errors if rows[2] or rows[3] is shorter than expected
                col_x0 = time_slot_numbers[i]["x0"] if i < len(time_slot_numbers) else 0
                col_x1 = time_slot_times[i]["x1_cell"] if i < len(time_slot_times) else 0
                columns.append({
                    "x0": col_x0,
                    "x1": col_x1,
                    "x_center": (col_x0 + col_x1) / 2,  # Column center
                    "data": []
                })
        
        # --- 5. Analyze Rows and Extract Data ---
        for i, row in enumerate(rows):
            if i < 4:  # Skip the time slot definition rows
                continue
            
            row_day = None
            min_x0 = min(cell["x0"] for cell in row) if row else float('inf')  # Find leftmost x0 (or infinity if row is empty)
            
            for cell in row:
                text = cell["text"]
                x0_cell = cell["x0"]
                x1_cell = cell["x1_cell"]
                cell_center = (x0_cell + x1_cell) / 2
                cell_width = x1_cell - x0_cell
                
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
                            pass # Cell not assigned
            
            
        # --- 6. Organize Extracted Data ---
        for j, col in enumerate(columns):
            # time_slot might not exist for every column.  Handle the error.
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

                # Split combined text (e.g.,  'MM Mr Alok MMDr Shankar MMDr Anshu'  )
                split_text = re.split(r'\s+(?=[A-Z][a-z]+\s[A-Z])', text)  # Split by spaces before names
                if len(split_text) > 1:
                    for k, part in enumerate(split_text):
                        if k == 0:
                           data.append({
                                'day': row_day,
                                'time': time_slot,
                                'subject': subject_match.group(1) if subject_match else None,
                                'room': room_match.group(1) if room_match else None,
                                'group': group_match.group(1) if group_match else None,
                                'raw_text':  part
                            })
                        else:
                            name_parts = part.strip().split()
                            if len(name_parts) >= 2:
                                data.append({
                                'day': row_day,
                                'time': time_slot,
                                'subject':  None,
                                'room': None,
                                'group':  None,
                                'raw_text':  part
                            })
                else:

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
    if timetable_data:
        for entry in timetable_data:
            print(entry)
    else:
        print("No data extracted.  Check the section name and PDF path.")
