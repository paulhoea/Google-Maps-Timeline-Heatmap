# Google-Maps-Timeline-Heatmap

Visualise your Google Maps Timeline data with Python and Folium!

<img width="551" height="423" alt="map" src="https://github.com/user-attachments/assets/ffe15c6b-3e47-44ea-913d-203af1dd917c" />

## Scope

This .py file imports Google Timeline data to generate an interactive heatmap and detail map of walking journeys.

Various filters can be configured to display only walks of a certain length, in certain areas, or on certain days. Various Geospatial and data processing techniques are used in the script to archive this efficiently.

## Guide

Input files: Google Maps Timeline Data (.json), District Shapefiles (.zip format), optionally Steps App Export Data (.csv)

Obtain Google Timeline data (usually found in Phone Settings "Location & privacy", not on the Google Account per default anymore). Relevant information can be found at [https://support.google.com/maps/answer/6258979?hl=en&co=GENIE.Platform%3DAndroid#zippy=%2Cturn-on-backup-on-your-device], ([see here](https://support.google.com/maps/thread/264641290?sjid=2994992130023812188-EU)) for details.

Optionally, also export data from [StepsApp](https://www.steps.app/de), which can be used to identify relevant days. If not available, relevant days can be set manually in the "Filters" section of the code. If steps data is provided, only days with (1) a certain amount of steps, (2) during daytime hours are counted. All of these heuristics are easily configurable code.

Shape files for district filtering (Vienna) are availible at [https://www.data.gv.at/katalog/datasets/2ee6b8bf-6292-413c-bb8b-bd22dbb2ad4b]. The same procedure can be adapted to different cities with relative ease, as geodata processing is kept flexible, not hard-coded.
