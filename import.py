#################
##### SETUP #####
#################

# %% Setup 
# Libraries
import json
import folium
import datetime
import pandas as pd
import numpy as np
from folium.plugins import HeatMap

# Filepaths
import_file = "/home/paul/Documents/Timeline/Timeline.json"
export_file = "/home/paul/Documents/Timeline/Table.csv"

# Filters
day_start = 6
day_end = 22
# start_date = '2025-01-01'
# end_date = '2025-12-31'
# start_date = '2025-10-02T00:00:00' # LINZ
# end_date = '2025-10-02T23:59:59'
start_date = '2025-10-08T00:00:00'
end_date = '2025-10-08T23:59:59'


# %% Import JSON and convert to table
with open(import_file, 'r') as file:
    data = json.load(file)

# the semantic segments encode relevant parts of the data
df = pd.json_normalize(data["semanticSegments"])

# %% Handle date filtering
# prepare for safe addition
df['startTimeTimezoneUtcOffsetMinutes'] = df['startTimeTimezoneUtcOffsetMinutes'].fillna(0)
df['endTimeTimezoneUtcOffsetMinutes'] = df['endTimeTimezoneUtcOffsetMinutes'].fillna(0)

# covert to date
df['startTime'] = pd.to_datetime(df['startTime'],utc=True)
df['endTime'] = pd.to_datetime(df['endTime'],utc=True)

# incorporate the timezone offset
df['startTime'] = df['startTime'] + pd.to_timedelta(df['startTimeTimezoneUtcOffsetMinutes'], unit='m')
df['endTime'] = df['endTime'] + pd.to_timedelta(df['endTimeTimezoneUtcOffsetMinutes'], unit='m')

# filter date
mask = (df['startTime'] >= start_date) & (df['startTime'] <= end_date)
filtered_df = df.loc[mask]

# %% Filter to keep only daytime hours
filtered_df = filtered_df[
    (filtered_df['startTime'].dt.hour >= day_start) & (filtered_df['startTime'].dt.hour < day_end) &
    (filtered_df['endTime'].dt.hour >= day_start) & (filtered_df['endTime'].dt.hour < day_end)
]
# %% Filter for Walking (and NaN, which are unassigned raw location information to be processed manually) segments
filtered_df['activity.topCandidate.type'].unique() # there would be other interesting modes, like skiing
filtered_df['activity.topCandidate.type'].value_counts(dropna=False) # many paths do not get assigned an activity, hence have to keep NaNs in the analysis

# Keep only WALKING and NaN (unassigned) segments
filtered_df = filtered_df[
    (filtered_df["activity.topCandidate.type"] == "WALKING")
    | (filtered_df["activity.topCandidate.type"].isna()) # included to keep data with timelinePath, which does not get assigned an activity type
]

# %% Optional: raw data export
# filtered_df['startTime'] = filtered_df['startTime'].dt.tz_localize(None)
# filtered_df['endTime'] = filtered_df['endTime'].dt.tz_localize(None)
# filtered_df.to_excel('test.xlsx', sheet_name='sheet1', index=False)

# %% Keep only travel (i.e. remove any visits)
filtered_df = filtered_df[filtered_df["visit.hierarchyLevel"].isna()] # presence of any visit.hierarchyLevel indicates a visit, thus not a travel. These are removed.



##################
### PROCESSING ###
##################

# %% drop (TODO:) obsoltete and empty columns
filtered_df = filtered_df.dropna(axis='columns', how='all')


# %% timeline_df separately
timeline_df = filtered_df[~filtered_df["timelinePath"].isna()]
timeline_df = timeline_df.dropna(axis='columns', how='all')

timelinePoints = []

for json_string in timeline_df['timelinePath']:
    for item in json_string:
        if 'point' in item:
            timelinePoints.append(item['point'])

# TODO: rename timelinePoints now that it turns into the data frame for further processing
points_df = pd.DataFrame({'point': timelinePoints})
points_df["timelineLat"] = points_df["point"].str.split('°, ').str[0].str.replace('°', '').astype(float)
points_df["timelineLon"] = points_df["point"].str.split('°, ').str[1].str.replace('°', '').astype(float)

points_df = points_df[["timelineLat", "timelineLon"]]

# %% remove timelinePath parts from segement df
filtered_df = filtered_df[filtered_df["timelinePath"].isna()]

# %% Split latLng string into separate lat and lng columns
filtered_df[['startLat', 'startLng']] = filtered_df['activity.start.latLng'].str.replace('°', '').str.split(',', expand=True).astype(float)
filtered_df[['endLat', 'endLng']] = filtered_df['activity.end.latLng'].str.replace('°', '').str.split(',', expand=True).astype(float)

# %% Heuristic: drop timelinePoints data if they are solitary, implying fast travel (e.g. public transport) being registered

points_df

#################
#### RESULTS ####
#################

# %% drop non-Vienna coordinates
filtered_df = filtered_df.query('startLat >= 48.092441 & startLat <= 48.349715 & startLng >= 16.136967 & startLng <= 16.627111')
points_df = points_df.query('timelineLat >= 48.092441 & timelineLat <= 48.349715 & timelineLon >= 16.136967 & timelineLon <= 16.627111')

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
for idx, row in timelinePoints.iterrows():
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
# %% Heatmap instead

h = folium.Map(location=[center_lat, center_lng], zoom_start=12)

HeatMap(timelinePoints).add_to(h)

h.save('/home/paul/heat_map.html')
# %%
