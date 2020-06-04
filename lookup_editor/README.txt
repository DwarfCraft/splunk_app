================================================
Overview
================================================

This app provides a user-interface for editing lookup files in Splunk.



================================================
Configuring Splunk
================================================
Install this app into Splunk by doing the following:

  1. Log in to Splunk Web and navigate to "Apps » Manage Apps" via the app dropdown at the top left of Splunk's user interface
  2. Click the "install app from file" button
  3. Upload the file by clicking "Choose file" and selecting the app
  4. Click upload
  5. Restart Splunk if a dialog asks you to

Once the app is installed, you can use can open the "Lookup Editor" app from the main launcher.



================================================
Known Limitations
================================================

1) The lookup editor is limited to editing files up to 10 MB. Files larger than this cannot be edited because it consume too much memory on some browsers.

2) The lookup editor does not enforce concurrency with CSV files. This means that if two users edit a lookup file at the same time, someone will lose changes.



================================================
Getting Support
================================================

Go to the following website if you need support:

     http://answers.splunk.com/answers/app/1724

You can access the source-code and get technical details about the app at:

     https://github.com/LukeMurphey/lookup-editor



================================================
Change History
================================================

+---------+------------------------------------------------------------------------------------------------------------------+
| Version |  Changes                                                                                                         |
+---------+------------------------------------------------------------------------------------------------------------------+
| 0.5     | Initial release                                                                                                  |
|---------|------------------------------------------------------------------------------------------------------------------|
| 0.6     | Added support for Splunk 5.0                                                                                     |
|         | Added limit for large lookup files (>10 MB)                                                                      |
|         | Fixed issues where the modular input failed to validate parameters correctly and log error messages              |
|---------|------------------------------------------------------------------------------------------------------------------|
| 0.7     | Fixed issue where the header and footer did not show on 6.0 due to a Javascript error                            |
|---------|------------------------------------------------------------------------------------------------------------------|
| 1.0     | Fixed issue that prevented the app from working with custom root endpoints                                       |
|         | Updated the app to work better on Splunk 6.1                                                                     |
|---------|------------------------------------------------------------------------------------------------------------------|
| 1.1     | Added warning when users attempt to delete the header row                                                        |
|         | Made the header row sticky such that it stays at the top of the page even when you scroll down                   |
|---------|------------------------------------------------------------------------------------------------------------------|
| 1.2     | Added ability to select how many entries to show on each page                                                    |
|---------|------------------------------------------------------------------------------------------------------------------|
| 1.3     | Added built-in backups of files and ability to load the previous version                                         |
|---------|------------------------------------------------------------------------------------------------------------------|
| 1.3.1   | Updated icon for Splunk 6.2                                                                                      |
|---------|------------------------------------------------------------------------------------------------------------------|
| 1.4.0   | Added ability to import CSV files in the editor                                                                  |
|---------|------------------------------------------------------------------------------------------------------------------|
| 1.4.1   | Fixed issue where some lookup files could not be loaded in some cases                                            |
|         | Fixed minor Javascript error that occurred if the server indicated that the lookup file couldn't be saved        |
|         | Backup file times now represent the date that the file was modified (not the date it was backed up)              |
|---------|------------------------------------------------------------------------------------------------------------------|
| 2.0.0   | Complete re-write, changes include:                                                                              |
|         |   * Support for KV store lookups                                                                                 |
|         |   * Refreshed UI style                                                                                           |
|         |   * Dropped Splunk 5.0 support                                                                                   |
|         |   * CSV lookups are now replicated (SHC support)                                                                 |
|---------|------------------------------------------------------------------------------------------------------------------|
| 2.0.1   | Workaround for XSS issue in Handsontable plugin                                                                  |
|---------|------------------------------------------------------------------------------------------------------------------|
| 2.0.2   | Eliminating XSS issue on file import                                                                             |
|---------|------------------------------------------------------------------------------------------------------------------|
| 2.0.3   | Fixing compatibility issue with IE 11                                                                            |
|         | Adding text to make it clear that KV store lookups will be automatically saved                                   |
|         | Fixing issue where the renderer was not styling the cells correctly                                              |
|---------|------------------------------------------------------------------------------------------------------------------|
| 2.1     | Fixed issue where lookup would fail to load in some cases                                                        |
|         | Added ability to make a user-specific lookup                                                                     |
|         | Updated the description of CSV lookups to note that CSV lookups do support SHC                                   |
|         | Fixed an issue where a value of "null" would appear in the editor sometimes                                      |
|         | Fixed an issue where the UI would not let you change the lookup name if new lookup creation failed               |
|         | Added sourcetyping of the lookup editor controller logs                                                          |
|         | App now detects if you are using an older version of Splunk that doesn't support KV store and hides KV options   |
|         | The editor no longer allows you to select a disabled app                                                         |
|         | The lookups list now includes the ability to filter on apps that only include KV lookups                         |
|---------|------------------------------------------------------------------------------------------------------------------|
| 2.1.1   | Fixed issue where local lookups would not appear in the list if the app did not have read permissions            |
|---------|------------------------------------------------------------------------------------------------------------------|
| 2.1.2   | Press CTRL + E on the lookup edit page for a blast from the past!                                                |
|---------|------------------------------------------------------------------------------------------------------------------|
| 2.2     | Added ability to load KV store collections entries from other users                                              |
|         | Updated icon                                                                                                     |
|         | Fixed issue where the first row of KV store lookups could not be removed                                         |
|---------|------------------------------------------------------------------------------------------------------------------|
| 2.3     | Updated the table editor (various bug fixes)                                                                     |
|         | Adding validation of numeric cells in KV lookups                                                                 |
|         | Adding validation of time cells in KV lookups                                                                    |
|         | Time values are now properly converted to epoch-seconds (a number) when being saved                              |
|         | Table is now re-rendered properly when switching user contexts                                                   |
|         | User interface improvements to the editor                                                                        |
|         | Added export option to the editor                                                                                |
|---------|------------------------------------------------------------------------------------------------------------------|
| 2.3.1   | Fixed some issues on the lookup creation page                                                                    |
|---------|------------------------------------------------------------------------------------------------------------------|
| 2.3.2   | Added ability to edit blank CSV files                                                                            |
|         | Editor now works even if ES is installed                                                                         |
|         | JSON blobs within columns can now be edited                                                                      |
|---------|------------------------------------------------------------------------------------------------------------------|
| 2.3.3   | Fixed issue where KV store lookups with boolean values didn't work on some versions of Splunk                    |
|         | Added support for Splunk 6.5                                                                                     |
|         | Fixed issue where you couldn't delete the first row on KV store lookups                                          |
|---------|------------------------------------------------------------------------------------------------------------------|
| 2.3.4   | Fixed issue where the app could cause Splunk to make world writable files                                        |
|---------|------------------------------------------------------------------------------------------------------------------|
| 2.4.0   | Added ability to open lookups in search                                                                          |
|         | Fixed issue where a KV store lookup with missing fields might cause the rows to not line up with the header      |
|---------|------------------------------------------------------------------------------------------------------------------|
| 2.5.0   | No longer allow KV store fields to be created with dollar-sign characters (not allowed by MongoDB)               |
|         | KV store lookups can now be disabled and enabled                                                                 |
|         | Fixed issue where a user-made lookup file that had it's permissions set to shared could not be opened            |
|         | Improved the styling of the lookups list page                                                                    |
|         | Updated the descriptions of the types of lookups on the new lookups page                                         |
|         | Fixed incompatibilty with the Mobile Access Add-on                                                               |
|---------|------------------------------------------------------------------------------------------------------------------|
| 2.6.0   | Added ability to refresh the lookup                                                                              |
|         | Fixed misaligned dropdown on the lookup list page                                                                |
|         | Added link to edit lookup permissions from the list page                                                         |
|         | Improved the list of users on the KV lookup editor to make it easier to use when lots of users exist             |
|         | Improved the icon                                                                                                |
|---------|------------------------------------------------------------------------------------------------------------------|
| 2.6.1   | Improving styling on Splunk 6.6                                                                                  |
|         | Fixing refresh button on the lookup editor page which didn't work in some case                                   |
|---------|------------------------------------------------------------------------------------------------------------------|
| 2.6.2   | CSV lookups with invalid characters can now be loaded                                                            |
|         | Added the search views to the app's navigation                                                                   |
|---------|------------------------------------------------------------------------------------------------------------------|
| 2.7.0   | Importing CSV files into KV store lookups is now supported                                                       |
|         | KV store lookup files will be opened in the "nobody" owner context by default now                                |
|         | Fixed error message when deleting KV store row entries on Splunk 6.6                                             |
|         | Edit ACLs page now opens in a new page                                                                           |
|---------|------------------------------------------------------------------------------------------------------------------|
| 2.7.1   | Fixing issue where lookups with spaces in the names were allowed                                                 |
|---------|------------------------------------------------------------------------------------------------------------------|
| 2.7.2   | Fixing issue where lookup saving would be considered a failure when replication could not be forced              |
|---------|------------------------------------------------------------------------------------------------------------------|
| 3.0.0   | Added support for Splunk 7.1                                                                                     |
|         | Numerous user interface enhancements                                                                             |
|         | Added ability to replicate lookup backup files in a Search Head Cluster                                          |
|         | Added a link to open a lookup in search from the lookup editor                                                   |
|         | Added a dialog that will guide the user in creating a lookup transform in order to open it in search             |
|         | Added support for editing on an iPad                                                                             |
|---------|------------------------------------------------------------------------------------------------------------------|
| 3.0.1   | Fixing issue where CSVs didn't loaded for some user names (such as those with slashes)                           |
|         | Fixing broken open-in-search link                                                                                |
|---------|------------------------------------------------------------------------------------------------------------------|
| 3.0.2   | Fixing issue where lookup saving would be considered a failure when replication could not be forced              |
|         | Added message noting that lookup file is being loaded                                                            |
|         | KV store lookup fields are correctly loaded when the fields are declared in transforms.conf                      |
|---------|------------------------------------------------------------------------------------------------------------------|
| 3.0.3   | Fixing issue where time fields could be mis-interpreting and saved as "NaN"                                      |
|         | Fixing double encoding issue causing lookups files to not be listed                                              |
|         | Fixing issue where lookups that were user-owned by a user with a slash couldn't be loaded or deleted             |
|         | New CSV lookup files are no longer created via direct access                                                     |
|         | Lookup creation was disallowed unnecessarily for CSVs for non-admins                                             |
|---------|------------------------------------------------------------------------------------------------------------------|
| 3.0.4   | Fixing issue where app was incompatible with apps that had copied components from the Lookup Editor              |
|         | Fixing issue where transform entry was made incorrectly for KV store lookups with a field name containing a space|
|---------|------------------------------------------------------------------------------------------------------------------|
| 3.0.5   | Lookup backup files are no longer replicated to the indexers                                                     |
|---------|------------------------------------------------------------------------------------------------------------------|
| 3.1.0   | Numerous improvements to the editor (sorting support, bug fixes, etc.)                                           |
|---------|------------------------------------------------------------------------------------------------------------------|
| 3.2.0   | Replication of KV store collections is now optional; the editor gives you the option to disable replication      |
|---------|------------------------------------------------------------------------------------------------------------------|
| 3.2.1   | Fixed issue where time values in KV lookups were being converted incorrectly                                     |
|---------|------------------------------------------------------------------------------------------------------------------|
| 3.3.0   | Added support for CIDR and array KV store field types                                                            |
|         | Fixed issue where time values in KV store lookups were being converted incorrectly                               |
|---------|------------------------------------------------------------------------------------------------------------------|
| 3.3.1   | Fixed error when attempting to edit KV store lookup file                                                         |
|---------|------------------------------------------------------------------------------------------------------------------|
| 3.3.2   | Fixed issue where filtering on the lookup list didn't work correctly in some cases                               |
|         | Lookups can now be created when using the free license                                                           |
|---------|------------------------------------------------------------------------------------------------------------------|
| 3.3.3   | Adding Python 3 support                                                                                          |
|---------|------------------------------------------------------------------------------------------------------------------|
| 3.4.0   | Added ability to search entries in the editor                                                                    |
|         | New KV store rows are no longer saved until the user sets a field                                                |
|         | Column name changes are done through a context menu which should make column renaming easier                     |
|         | Replaced the handsontable library with jexcel                                                                    |
|---------|------------------------------------------------------------------------------------------------------------------|
| 3.4.1   | Fixed issue where values with some characters (such as "<" and ">") failed to appear                             |
+---------+------------------------------------------------------------------------------------------------------------------+
