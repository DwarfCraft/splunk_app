Carousel Viz ver 1.1.2

Daniel Spavin
daniel@spavin.net

Version Support
7.2, 7.1, 7.0, 6.6, 6.5, 6.4

Who is this app for?
This app is for anyone who wants to display several metrics on a small area of a dashboard.

How does the app work?
This app provides a visualization that you can use in your own apps and dashboards.

To use it in your dashboards, simply install the app, and create a search that provides the values you want to display.

Usecases for the Heat Map Visualization:
Displaying server metrics like CPU, Memory, I/O, and Disk usage over time
Comparing sales volume by category over time
Showing related application metrics in a discreet dashboard panel
Highlighting any metrics relative to other entities
The following fields can be used in the search:
_time (required): The easiest way to construct a search is to use the | timechart command, with a by clause.
category fields (required): Each field name will become a label on the side, with the values being used to set the color based on thresholds. The order of the fields determines the order shown in the viz.
Example Search
| gentimes start=-7 increment=4h 
| eval "Server Availability"=random()%100, "Customer Satisfaction"=random()%100,"Server Performance"=random()%100, _time=starttime 
| table _time, "Server Availability","Customer Satisfaction","Server Performance"

Tokens
Tokens are generated each time you click a cell. This can be useful if you want to populate another panel on the dashboard with a custom search, or link to a new dashboard with the tokens carrying across.

Value: This is the numeric field for the cell you clicked. Default value: $hm_token_value$
Label: This is the field name for the cell you clicked. Default value: $hm_token_label$
Time: This is the '_time' field for the selection. Default value: $hm_token_time$
Limits
The visualization is bound by the following limits:

Total results: 50,000
Release Notes
v 1.1.0
Added the option of putting the date in the tooltip. Several date formats are available to use.
You can now turn off animation in the options menu.
The visualization now resizes when you resize the panel.
  

v 1.0.0
Initial version
Issues and Limitations
If you have a bug report or feature request, please contact daniel@spavin.net

Privacy
No personally identifiable information is logged or obtained in any way through this visualization.

For support
Send email to daniel@spavin.net

Support is not guaranteed and will be provided on a best effort basis.

Third-Party Libraries
This visualization uses ApexCharts