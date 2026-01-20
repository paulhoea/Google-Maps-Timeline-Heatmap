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
from sklearn.neighbors import BallTree
import matplotlib.pyplot as plt

# Filepaths
import_file = "/home/paul/Documents/Timeline/Timeline.json"
export_file = "/home/paul/Documents/Timeline/Table.csv"
steps_file = "/home/paul/Documents/Timeline/StepsAppDataExport/activity-export-hourly.csv"

# Filters
day_start = 6
day_end = 22
start_date = '2025-01-01'
end_date = '2025-12-31'
# start_date = '2025-10-02T00:00:00' # LINZ
# end_date = '2025-10-02T23:59:59'
# start_date = '2025-10-08T00:00:00'
# end_date = '2025-10-08T23:59:59'
steps_treshold = 12000


# %% Import JSON and convert to table
with open(import_file, 'r') as file:
    data = json.load(file)

# the semantic segments encode relevant parts of the data, the steps are imported from a separate app
df = pd.json_normalize(data["semanticSegments"])
steps_df = pd.read_csv(steps_file, delimiter=";")
steps_df = steps_df.iloc[1:]

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
# filtered_df.to_excel('/home/paul/test.xlsx', sheet_name='sheet1', index=False)

# %% Keep only travel (i.e. remove any visits)
filtered_df = filtered_df[filtered_df["visit.hierarchyLevel"].isna()] # presence of any visit.hierarchyLevel indicates a visit, thus not a travel. These are removed.


###################################
### RELEVANT DAY IDENTIFICATION ###
###################################

# %%
steps_df["date"] = pd.to_datetime(steps_df["date"],utc=True)
steps_df["day"] = steps_df["date"].dt.date
steps_df["time"] = steps_df["date"].dt.hour
steps_df["steps"] = pd.to_numeric(steps_df["steps"])

steps_df = steps_df[(steps_df["date"] >= start_date) & (steps_df["date"] <= end_date)]
steps_df = steps_df[(steps_df["time"] >= day_start) & (steps_df["time"] <= day_end)]


steps_df = steps_df.groupby("day")["steps"].sum().reset_index(name="steps")

# Preview whether the steps cutoff is chosen appropriately
plt.hist(steps_df["steps"], bins=range(min(steps_df["steps"]), max(steps_df["steps"]) + 2000, 2000))
plt.axvline(steps_treshold, color='k', linestyle='dashed', linewidth=1)
plt.show() 

# %% keep only relevant, as defined by steps threshold
steps_df["relevant"] = steps_df["steps"] > steps_treshold



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
filtered_df[['startLat', 'startLon']] = filtered_df['activity.start.latLng'].str.replace('°', '').str.split(',', expand=True).astype(float)
filtered_df[['endLat', 'endLon']] = filtered_df['activity.end.latLng'].str.replace('°', '').str.split(',', expand=True).astype(float)

# %% Heuristic: drop timelinePoints data if they are solitary, implying fast travel (e.g. public transport) being registered

# Convert to radians
points_df[['timelineRadLat', 'timelineRadLon']] = np.radians(points_df[['timelineLat', 'timelineLon']].values)
max_distance_km=1.0
    
# Build tree
tree = BallTree(points_df[['timelineRadLat', 'timelineRadLon']], metric='haversine')

# Find points to keep
keep_mask = np.ones(len(points_df), dtype=bool)

for i in range(len(keep_mask)):
    if not keep_mask[i]:
        continue
    # Find k=2 nearest neighbors (itself + 1 other)
    distances, indices = tree.query([points_df[['timelineRadLat', 'timelineRadLon']].iloc[i].values], k=2)
    # Check distance to nearest neighbor (index 1, since index 0 is itself)
    if len(distances[0]) > 1 and distances[0][1] > max_distance_km/6371.0:
        keep_mask[i] = False

points_df = points_df[keep_mask].reset_index(drop=True)


# %% Heuristic: remove certain areas (TODO: extend to a bespoke district filter)

filtered_df = filtered_df.query('not (startLat >= 48.205372 & startLat <= 48.216725 & startLon >= 16.337250 & startLon <= 16.362453)')
points_df = points_df.query('not (timelineLat >= 48.205372 & timelineLat <= 48.216725 & timelineLon >= 16.337250 & timelineLon <= 16.362453)')


#################
#### RESULTS ####
#################
# %% Display result on map

# drop non-Vienna coordinates
filtered_df = filtered_df.query('startLat >= 48.092441 & startLat <= 48.349715 & startLon >= 16.136967 & startLon <= 16.627111')
points_df = points_df.query('timelineLat >= 48.092441 & timelineLat <= 48.349715 & timelineLon >= 16.136967 & timelineLon <= 16.627111')


# Calculate the center point for the map
center_lat = (filtered_df['startLat'].mean() + filtered_df['endLat'].mean()) / 2
center_lng = (filtered_df['startLon'].mean() + filtered_df['endLon'].mean()) / 2

# Create a map centered on your data
m = folium.Map(location=[center_lat, center_lng], zoom_start=12)

# Add lines for each segement
for idx, row in filtered_df.iterrows():
    folium.PolyLine(
        locations=[
            [row['startLat'], row['startLon']], 
            [row['endLat'], row['endLon']]
        ],
        color='blue',
        weight=2,
        opacity=0.6
    ).add_to(m)

# add dots for each point
for idx, row in points_df.iterrows():
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

# Heatmap preview

h = folium.Map(location=[center_lat, center_lng], zoom_start=12)

HeatMap(points_df[["timelineLat", "timelineLon"]]).add_to(h)

h.save('/home/paul/heat_map.html')
# %%
