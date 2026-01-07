# %% Setup 
# Libraries
import json
import folium
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
# start_time = '2025-10-02T00:00:00' # LINZ
# end_time = '2025-10-02T23:59:59'
start_time = '2025-10-08T00:00:00'
end_time = '2025-10-08T23:59:59'


# %% Import JSON and convert to table
with open(import_file, 'r') as file:
    data = json.load(file)

df = pd.json_normalize(data["semanticSegments"])

# %% Assign as datetime column
df['startTime'] = pd.to_datetime(df['startTime'],utc=True)
df['endTime'] = pd.to_datetime(df['endTime'],utc=True)

# %% Date Filters
mask = (df['startTime'] >= start_time) & (df['startTime'] <= end_time)
filtered_df = df.loc[mask]

# %% Filter to keep only daytime hours
filtered_df = filtered_df[
    (filtered_df['startTime'].dt.hour >= day_start) & (filtered_df['startTime'].dt.hour < day_end) &
    (filtered_df['endTime'].dt.hour >= day_start) & (filtered_df['endTime'].dt.hour < day_end)
]

# %% Filter for Walking (and NaN) segments
filtered_df['activity.topCandidate.type'].unique() # there would be other interesting modes, like skiing
filtered_df['activity.topCandidate.type'].value_counts(dropna=False) # many paths do not get assigned an activity, hence have to keep NaNs in the analysis

filtered_df.columns # TODO: look into that more

# Keep only WALKING and NaN (unassigned) segments
filtered_df = filtered_df[
    (filtered_df["activity.topCandidate.type"] == "WALKING")
    | (filtered_df["activity.topCandidate.type"].isna()) # included to keep data with timelinePath, which does not get assigned an activity type
]

# %%
# filtered_df['startTime'] = filtered_df['startTime'].dt.tz_localize(None)
# filtered_df['endTime'] = filtered_df['endTime'].dt.tz_localize(None)
# filtered_df.to_excel('test.xlsx', sheet_name='sheet1', index=False)


# %% Keep only travel (i.e. remove any visits)
filtered_df = filtered_df[filtered_df["visit.hierarchyLevel"].isna()] # presence of any visit.hierarchyLevel indicates a visit, thus not a travel. These are removed.

# %% TODO: Extract coordinates from timeline data
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


# %% timeline_df separately
timeline_df = filtered_df[~filtered_df["timelinePath"].isna()]
timeline_df = timeline_df.dropna(axis='columns', how='all')

all_points = []

for json_string in timeline_df['timelinePath']:
    for item in json_string:
        if 'point' in item:
            all_points.append(item['point'])

# TODO: rename all_points now that it turns into the data frame for further processing
all_points = pd.DataFrame({'point': all_points})
all_points["timelineLat"] = all_points["point"].str.split('°, ').str[0].str.replace('°', '').astype(float)
all_points["timelineLon"] = all_points["point"].str.split('°, ').str[1].str.replace('°', '').astype(float)

# %% remove timelinePath parts from segement df
filtered_df = filtered_df[filtered_df["timelinePath"].isna()]

# %% Split latLng string into separate lat and lng columns

# TODO: concat these values into existing if needed

filtered_df[['startLat', 'startLng']] = filtered_df['activity.start.latLng'].str.replace('°', '').str.split(',', expand=True).astype(float)
filtered_df[['endLat', 'endLng']] = filtered_df['activity.end.latLng'].str.replace('°', '').str.split(',', expand=True).astype(float)

# %% drop non-Vienna coordinates
filtered_df.query('startLat >= 48.092441 & startLat <= 48.349715 & startLng >= 16.136967 & startLng <= 16.627111')


# %% Display result on map
# Calculate the center point for the map
center_lat = (filtered_df['startLat'].mean() + filtered_df['endLat'].mean()) / 2
center_lng = (filtered_df['startLng'].mean() + filtered_df['endLng'].mean()) / 2

# Create a map centered on your data
m = folium.Map(location=[center_lat, center_lng], zoom_start=12)

# Add lines for each segement
for idx, row in filtered_df.iterrows():
    folium.PolyLine(
        locations=[
            [row['startLat'], row['startLng']], 
            [row['endLat'], row['endLng']]
        ],
        color='blue',
        weight=2,
        opacity=0.6
    ).add_to(m)

# add dots for each point
for idx, row in all_points.iterrows():
    folium.CircleMarker(
        location=[row['timelineLat'], row['timelineLon']],
        radius=3,
        color='red',
        fill=True,
        fillColor='red'
    ).add_to(m)

# Save and display
m.save('/home/paul/routes_map.html')
# m  # If in Jupyter, this will display inline
# %%
