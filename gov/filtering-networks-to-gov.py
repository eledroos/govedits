import pandas as pd

# Load ARIN data from CSV
file_path = 'networks.csv'  # Replace with file path
arin_data = pd.read_csv(file_path)

# Combine all patterns for filtering government-related entities
comprehensive_patterns = [
    # Original patterns
    r"\bstate of\b", r"\bdepartment of\b", r"\bcity of\b", r"\bcounty of\b", r"\bunited states\b",
    r"\bu\.s\.\b", r"\bsenate\b", r"\bhouse of representatives\b", r"\blegislature\b",
    r"\battorney general\b", r"\bsupreme court\b", r"\boffice of\b", r"\badministrative office\b",
    r"\binformation technology\b", r"\bfederal\b", r"\bnational\b",

    # Expanded patterns
    r"\bassembly\b", r"\blaw enforcement\b", r"\bpolice department\b", r"\bsheriff\b", r"\bcorrections\b",
    r"\bparole board\b", r"\bjustice\b", r"\bpublic safety\b", r"\bhighway patrol\b", r"\bemergency management\b",
    r"\bhomeland security\b", r"\bboard of education\b", r"\bschool district\b", r"\bjudicial branch\b",
    r"\bdistrict court\b", r"\badministrative office of the courts\b", r"\btransportation department\b",
    r"\binfrastructure authority\b", r"\bpublic health\b", r"\bmental health\b", r"\bchildren and families\b",
    r"\btaxation authority\b", r"\beconomic development\b", r"\barmed forces\b", r"\bnational guard\b",
    r"\bveterans affairs\b", r"\benvironmental protection\b", r"\bnatural resources\b",

    # Exhaustive patterns
    r"\bmetropolitan\b", r"\bmunicipality of\b", r"\bmunicipal government\b", r"\btown of\b", r"\bvillage of\b",
    r"\bborough of\b", r"\bcounty clerk\b", r"\bclerk of courts\b", r"\btownship of\b", r"\bschool board\b",
    r"\bdistrict board\b", r"\butilities commission\b", r"\butilities authority\b", r"\bwaterworks\b",
    r"\bwastewater authority\b", r"\bhousing development authority\b", r"\bpublic housing\b",
    r"\bregional planning commission\b", r"\bplanning council\b", r"\bpublic information office\b",
    r"\boffice of the governor\b", r"\bmayor’s office\b", r"\bcabinet office\b", r"\bstate executive office\b",
    r"\baviation authority\b", r"\bpublic transit\b", r"\btransportation department\b", r"\bshipping\b",
    r"\bports authority\b", r"\bhospital authority\b", r"\bcommunity health\b", r"\bpublic assistance\b",
    r"\bchild welfare\b", r"\bfamily services\b", r"\bmedicaid office\b", r"\bfish and wildlife\b",
    r"\benvironmental health\b", r"\bland management\b", r"\bwater district\b", r"\bgeological survey\b",
    r"\bfire department\b", r"\brescue squad\b", r"\bdisaster management\b", r"\bhazard mitigation\b",
    r"\blibrary board\b", r"\barchives\b", r"\bhistorical society\b", r"\bcultural resources\b",
    r"\bredevelopment authority\b", r"\beconomic development corporation\b", r"\bsmall business administration\b",
    r"\bcommerce department\b", r"\bpublic works\b", r"\binfrastructure agency\b", r"\bgovernment services\b",
    r"\bagency of\b", r"\badministration of\b",
]

# Filter the ARIN data using the comprehensive patterns
filtered_data = arin_data[
    arin_data['Org Name'].str.contains('|'.join(comprehensive_patterns), case=False, na=False)
]

# Remove duplicates and reset index for clarity
filtered_data = filtered_data.drop_duplicates().reset_index(drop=True)

# Save the final dataset (optional)
filtered_data.to_csv('/mnt/data/filtered_government_organizations.csv', index=False)

# Display the final dataset to user (optional)
import ace_tools as tools; tools.display_dataframe_to_user(name="Exhaustive Government Agencies and IP Ranges", dataframe=filtered_data)
