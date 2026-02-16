#################
##### SETUP #####
#################

# %% Setup 
# Libraries
import json
import folium
import datetime
# import shapely
import pandas as pd
import geopandas as gpd
import numpy as np
from folium.plugins import HeatMap
from sklearn.neighbors import BallTree
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

# Filepaths
import_file = "/home/paul/Documents/Timeline/Timeline.json"
export_file = "/home/paul/Documents/Timeline/Table.csv"
steps_file = "/home/paul/Documents/Timeline/StepsAppDataExport/activity-export-hourly.csv"
district_file = "/home/paul/Documents/Timeline/Shapefiles/WFS GetFeature (SHP)-17.zip"

# Filters
day_start = 6
day_end = 22
start_date = '2025-01-01'
end_date = '2025-12-31'
steps_treshold = 12000
districts_exclude = [1010, 1060, 1070, 1080, 1090]
areas_exclude = [["48.206999", "48.219465", "16.397566", "16.415896"]]
# Optional: skips day identification heuristic via step counting, instead sets manual dates
relevant_days = None # format for manual entry: ["2025-12-29", "2025-01-01"]

# %% Import JSON and convert to table
with open(import_file, 'r') as file:
    data = json.load(file)

# the semantic segments encode relevant parts of the data, step counts are imported from a separate app
df = pd.json_normalize(data["semanticSegments"])

# load steps data for use in filtering
if relevant_days is None:
    steps_df = pd.read_csv(steps_file, delimiter=";")
    steps_df = steps_df.iloc[1:]

# load district outlines for use in filtering
districts_gdf = gpd.read_file(district_file)




#####################################
### DATE PROCESSING AND FILTERING ###
#####################################

# %% Handle date filtering
# prepare for safe addition
df['startTimeTimezoneUtcOffsetMinutes'] = df['startTimeTimezoneUtcOffsetMinutes'].fillna(0)
df['endTimeTimezoneUtcOffsetMinutes'] = df['endTimeTimezoneUtcOffsetMinutes'].fillna(0)

# covert to date
df['startTime'] = pd.to_datetime(df['startTime'],utc=True)
df['endTime'] = pd.to_datetime(df['endTime'],utc=True)
df["date"] = df["startTime"].dt.date

# incorporate the timezone offset
df['startTime'] = df['startTime'] + pd.to_timedelta(df['startTimeTimezoneUtcOffsetMinutes'], unit='m')
df['endTime'] = df['endTime'] + pd.to_timedelta(df['endTimeTimezoneUtcOffsetMinutes'], unit='m')

# filter relevant date range
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

# %% Keep only travel (i.e. remove any visits from semanticSegments)
filtered_df = filtered_df[filtered_df["visit.hierarchyLevel"].isna()] # presence of any visit.hierarchyLevel indicates a visit, thus not a travel. These are removed.




###################################
### RELEVANT DAY IDENTIFICATION ###
###################################

# %%
if relevant_days is None: # use stepsapp data
    steps_df["date_utc"] = pd.to_datetime(steps_df["date"],utc=True)
    steps_df["time"] = steps_df["date_utc"].dt.hour
    steps_df["date"] = steps_df["date_utc"].dt.date
    steps_df["steps"] = pd.to_numeric(steps_df["steps"])

    steps_df = steps_df[(steps_df["date_utc"] >= start_date) & (steps_df["date_utc"] <= end_date)]
    steps_df = steps_df[(steps_df["time"] >= day_start) & (steps_df["time"] <= day_end)]


    steps_df = steps_df.groupby("date")["steps"].sum().reset_index(name="steps")

    # Preview whether the steps cutoff is chosen appropriately
    plt.hist(steps_df["steps"], bins=range(min(steps_df["steps"]), max(steps_df["steps"]) + 2000, 2000))
    plt.axvline(steps_treshold, color='k', linestyle='dashed', linewidth=1)
    plt.show() 

    # keep only relevant, as defined by steps threshold
    steps_df["relevant"] = steps_df["steps"] > steps_treshold
    steps_df.drop(columns = ["steps"], inplace = True) #axis = 1, - removed due to pandas update

    filtered_df = filtered_df.merge(steps_df)

    filtered_df = filtered_df[filtered_df["relevant"] == True] # for further processing
    steps_df = steps_df[steps_df["relevant"] == True] # not used later, but can be viewed to review the heuristic results

else: # use user-set dates from "filters" section in the beginning
    steps_df = pd.DataFrame({
        'date': pd.date_range(start=start_date, end=end_date, freq='D')
    })
    steps_df['relevant'] = steps_df['date'].isin(pd.to_datetime(relevant_days))
    filtered_df = filtered_df[filtered_df["relevant"] == True] # for further processing


##################
### PROCESSING ###
##################

# %% drop obsoltete and empty columns for easier viewing
filtered_df = filtered_df.dropna(axis='columns', how='all')

# %% timeline_df processed separately, into timelinePoints (df) for visualisation, and timelinePoints_separate (list) for (TODO) forthcoming testing
timeline_df = filtered_df[~filtered_df["timelinePath"].isna()]
timeline_df = timeline_df.dropna(axis='columns', how='all')

# remove timelinePath parts from segement df
segments_df = filtered_df[filtered_df["timelinePath"].isna()]

# split latLng string into separate lat and lng columns
segments_df[['startLat', 'startLon']] = segments_df['activity.start.latLng'].str.replace('°', '').str.split(',', expand=True).astype(float)
segments_df[['endLat', 'endLon']] = segments_df['activity.end.latLng'].str.replace('°', '').str.split(',', expand=True).astype(float)

# further process timelinePoints data separated from main df
timelinePoints = []

# split timeline rows into list items
for json_string in timeline_df['timelinePath']:
    timelinePoints.append(pd.json_normalize(json_string)) # more detailed format (list of dfs) for a later test
    
# process list items into relevant columns within the list
for item in timelinePoints:
    item["timelineLat"] = item["point"].str.split('°, ').str[0].str.replace('°', '').astype(float)
    item["timelineLon"] = item["point"].str.split('°, ').str[1].str.replace('°', '').astype(float)
    item["time"] = pd.to_datetime(item["time"],utc=True)
    item["date"] = item["time"].dt.date
    item = item.drop(columns = ["point"], inplace=True) # axis=1, 

# concatonate list into single dataframe for visualisation
points_df = pd.concat(timelinePoints)


#########################
### HEURISTIC FILTERS ###
#########################

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




# %% Heuristic: remove selected districts

# convert points to GeoDataFrame
points_df = gpd.GeoDataFrame(
    points_df,
    geometry=gpd.points_from_xy(points_df['timelineLon'], points_df['timelineLat']),
    crs='EPSG:4326'
)

# Reproject points to match the shapefile's CRS
points_df = points_df.to_crs(districts_gdf.crs)

# Spatial join to find which district each point is in
points_df = gpd.sjoin(points_df, districts_gdf, how='left', predicate='within')

# unify format
points_df = points_df[["time", "timelineLat", "timelineLon", "date", "timelineRadLat", "timelineRadLon", "DISTRICT_C"]]

# apply filter
points_df = points_df[~points_df["DISTRICT_C"].isin(districts_exclude)]

# similarly process segments_df:
# convert segments df to GeoDataFrame
start_points = gpd.GeoDataFrame(
    segments_df,
    geometry=gpd.points_from_xy(segments_df['startLon'], segments_df['startLat']),
    crs='EPSG:4326'
).to_crs(districts_gdf.crs)

end_points = gpd.GeoDataFrame(
    segments_df,
    geometry=gpd.points_from_xy(segments_df['endLon'], segments_df['endLat']),
    crs='EPSG:4326'
).to_crs(districts_gdf.crs)

# Separate out start or end coordinates matched with district info from the shapefile
start_joined = gpd.sjoin(start_points, districts_gdf[['geometry', 'DISTRICT_C']], 
                         how='left', predicate='within', rsuffix='_start')
end_joined = gpd.sjoin(end_points, districts_gdf[['geometry', 'DISTRICT_C']], 
                       how='left', predicate='within', rsuffix='_end')

# Combine the district information back into original df
segments_df['start_DISTRICT_C'] = start_joined['DISTRICT_C'].values
segments_df['end_DISTRICT_C'] = end_joined['DISTRICT_C'].values

# remove districts if contained in start or end df
segments_df = segments_df[~segments_df["start_DISTRICT_C"].isin(districts_exclude)]
segments_df = segments_df[~segments_df["end_DISTRICT_C"].isin(districts_exclude)]


# %% Heuristic: remove pre-defined areas

# segments_df = segments_df.query('startLat >= ' + areas_exclude[0][0] + ' & startLat <= ' + areas_exclude[0][1] + ' & startLon >= ' + areas_exclude[0][2] + ' & startLon  <= ' + areas_exclude[0][3])
# points_df = points_df.query('timelineLat >= ' + areas_exclude[0][0] + ' & timelineLat <= ' + areas_exclude[0][1] + ' & timelineLon >= ' + areas_exclude[0][2] + ' & timelineLon  <= ' + areas_exclude[0][3])

for item in areas_exclude:
    segments_df = segments_df.query('not(startLat >= ' + item[0] + ' & startLat <= ' + item[1] + ' & startLon >= ' + item[2] + ' & startLon  <= ' + item[3] + ')') 
    points_df = points_df.query('not(timelineLat >= ' + item[0] + ' & timelineLat <= ' + item[1] + ' & timelineLon >= ' + item[2] + ' & timelineLon  <= ' + item[3] + ')')




##################
#### ANALYSIS ####
##################

# %% count left and right turns
for item in timelinePoints:
    for i in range(2, len(item)):
        # Get the three consecutive points
        lat1, lon1 = item.loc[i-2, 'timelineLat'], item.loc[i-2, 'timelineLon']
        lat2, lon2 = item.loc[i-1, 'timelineLat'], item.loc[i-1, 'timelineLon']
        lat3, lon3 = item.loc[i, 'timelineLat'], item.loc[i, 'timelineLon']
        
        # Calculate the two vectors
        dlat1 = lat2 - lat1
        dlon1 = lon2 - lon1
        dlat2 = lat3 - lat2
        dlon2 = lon3 - lon2
        
        # Calculate cross product
        cross_product = dlat1 * dlon2 - dlon1 * dlat2
        
        # Classify the turn
        threshold = 1e-6 # this is arbitrary and can be done with other values, but this only affects what degree of movment gets counted as a turn, not turn ratios
        if cross_product > threshold:
            item.loc[i, 'turn'] = 'left'
        elif cross_product < -threshold:
            item.loc[i, 'turn'] = 'right'
        else:
            item.loc[i, 'turn'] = 'straight'

pd.concat(timelinePoints)["turn"].value_counts()


#################
#### RESULTS ####
#################
# %% Display result on map

# drop non-Vienna coordinates
segments_df = segments_df.query('startLat >= 48.092441 & startLat <= 48.349715 & startLon >= 16.136967 & startLon <= 16.627111')
points_df = points_df.query('timelineLat >= 48.092441 & timelineLat <= 48.349715 & timelineLon >= 16.136967 & timelineLon <= 16.627111')


# Calculate the center point for the map
center_lat = (segments_df['startLat'].mean() + segments_df['endLat'].mean()) / 2
center_lng = (segments_df['startLon'].mean() + segments_df['endLon'].mean()) / 2

# Create a map centered on your data
m = folium.Map(location=[center_lat, center_lng], zoom_start=12) #, tiles="CartoDB positron")

# Add lines for each segement
for idx, row in segments_df.iterrows():
    folium.PolyLine(
        locations=[
            [row['startLat'], row['startLon']], 
            [row['endLat'], row['endLon']]
        ],
        color='blue',
        weight=2,
        opacity=0.6,
        tooltip=row["date"]
    ).add_to(m)

# assign colours to each day
min_date = points_df['date'].min()
max_date = points_df['date'].max()
days_from_min = (points_df['date'] - min_date).apply(lambda x: x.days)
max_days = (max_date - min_date).days

if max_days > 0:
    normalized = days_from_min / max_days
else:
    normalized = np.zeros(len(points_df))

# Use a colormap (hsv, rainbow, or jet are good for hue progression)
cmap = plt.get_cmap('hsv')  # or 'rainbow', 'jet', 'turbo'
points_df['colour'] = normalized.apply(lambda x: mcolors.to_hex(cmap(x)))

# district outlines
folium.GeoJson(
    districts_gdf.select_dtypes(exclude=["datetime64[ns]", "datetime64[ns, UTC]"]),
    name="Districts",
    style_function=lambda feature: {
        "fillColor": "#ffa6a6",
        "color": "#ff6161",
        "weight": 1,
        "fillOpacity": 0.4,
    },
).add_to(m)

# add dots for each point
for idx, row in points_df.iterrows():
    folium.CircleMarker(
        location=[row['timelineLat'], row['timelineLon']],
        radius=3,
        color=row["colour"],
        fill=True,
        fillColor='red',
        tooltip=row["date"]
    ).add_to(m)

# Save and display
m.save('/home/paul/routes_map.html')
# m  # If in Jupyter, this will display inline

# Heatmap preview

h = folium.Map(location=[center_lat, center_lng], zoom_start=12)

# district outlines
folium.GeoJson(
    districts_gdf.select_dtypes(exclude=["datetime64[ns]", "datetime64[ns, UTC]"]),
    name="Districts",
    style_function=lambda feature: {
        "fillColor": "#ffa6a6",
        "color": "#ff6161",
        "weight": 1,
        "fillOpacity": 0.4,
    },
).add_to(h)

HeatMap(points_df[["timelineLat", "timelineLon"]]).add_to(h)

h.save('/home/paul/heat_map.html')
# %%
