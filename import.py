# %% Setup 
# Libraries
import json
import datetime
import pandas as pd
import numpy as np

# Filepaths
import_file = "/home/paul/Documents/Timeline/Timeline.json"
export_file = "/home/paul/Documents/Timeline/Table.csv"

# Filters
day_start = 6
day_end = 22
# start_date = '2025-01-01'
# end_date = '2025-12-31'
start_time = '2025-10-02T00:00:00' # LINZ
end_time = '2025-10-02T23:59:59'


# %% Import JSON and convert to table
with open(import_file, 'r') as file:
    data = json.load(file)

df = pd.json_normalize(data["semanticSegments"])

# %% Assign as datetime column
df['startTime'] = pd.to_datetime(df['startTime'],utc=True)
df['endTime'] = pd.to_datetime(df['endTime'],utc=True)

# %% Filter for Walking (and NaN) segments
df['activity.topCandidate.type'].unique() # there would be other interesting modes, like skiing
df['activity.topCandidate.type'].value_counts(dropna=False) # many paths do not get assigned an activity, hence have to keep NaNs in the analysis

df.columns # TODO: look into that more

# Keep only WALKING and NaN (unassigned) segments
filtered_df = df[
    (df["activity.topCandidate.type"] == "WALKING") |
    (df["activity.topCandidate.type"].isna()) # included to keep data with timelinePath, which does not get assigned an activity type
]

# %% Keep only travel (i.e. remove any visits)
filtered_df = filtered_df[filtered_df["visit.hierarchyLevel"].isna()] # presence of any visit.hierarchyLevel indicates a visit, thus not a travel. These are removed.

# %% Date Filters
mask = (filtered_df['startTime'] >= start_time) & (filtered_df['startTime'] <= end_time)
filtered_df = filtered_df.loc[mask]

# %% Filter to keep only daytime hours
filtered_df = filtered_df[
    (filtered_df['startTime'].dt.hour >= day_start) & (filtered_df['startTime'].dt.hour < day_end) &
    (filtered_df['endTime'].dt.hour >= day_start) & (filtered_df['endTime'].dt.hour < day_end)
]

# %% Extract coordinates from timeline data
filtered_df['startLat'] = (filtered_df['timelinePath']
                           .str[0]                    # Get first element in list
                           .str['point']              # Get 'point' field
                           .str.split('°, ')          # Split on degree symbol and comma
                           .str[0]                    # Get first part (latitude)
                           .str.replace('°', '')      # Remove degree symbol
                           .astype(float))            # Convert to float

filtered_df['startLng'] = (filtered_df['timelinePath']
                           .str[0]                    # Get first element in list
                           .str['point']              # Get 'point' field
                           .str.split('°, ')          # Split on degree symbol and comma
                           .str[1]                    # Get second part (longitude)
                           .str.replace('°', '')      # Remove degree symbol
                           .astype(float))            # Convert to float

filtered_df['endLat'] = (filtered_df['timelinePath']
                         .str[-1]                    # Get last element in list
                         .str['point']               # Get 'point' field
                         .str.split('°, ')           # Split on degree symbol and comma
                         .str[0]                     # Get first part (latitude)
                         .str.replace('°', '')       # Remove degree symbol
                         .astype(float))             # Convert to float

filtered_df['endLng'] = (filtered_df['timelinePath']
                         .str[-1]                    # Get last element in list
                         .str['point']               # Get 'point' field
                         .str.split('°, ')           # Split on degree symbol and comma
                         .str[1]                     # Get second part (longitude)
                         .str.replace('°', '')       # Remove degree symbol
                         .astype(float))             # Convert to float

# Example
# print(filtered_df["timelinePath"][53455])


# %% drop (TODO:) obsoltete and empty columns
filtered_df = filtered_df.dropna(axis='columns', how='all')



# %% Split latLng string into separate lat and lng columns

# TODO: concat these values into existing

#filtered_df[['startLat', 'startLng']] = filtered_df['activity.start.latLng'].str.replace('°', '').str.split(',', expand=True).astype(float)
#filtered_df[['endLat', 'endLng']] = filtered_df['activity.end.latLng'].str.replace('°', '').str.split(',', expand=True).astype(float)

# %% drop non-Vienna coordinates
filtered_df.query('startLat >= 48.092441 & startLat <= 48.349715 & startLng >= 16.136967 & startLng <= 16.627111')

