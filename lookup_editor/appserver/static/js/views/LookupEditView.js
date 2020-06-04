/**
 * This view provide a way to edit lookup files within Splunk.
 * 
 * Below is a list of major components that this view relies upon:
 * 
 * LookupEditView
 *   |--- LookupTransformCreateView: is used to open lookups in search and make the transform to make them searchable
 *   |--- KVStoreFieldEditor: is used to creating and editing the KV store schema
 *   |--- TableEditorView: the main table where the editing occurs (using Handsontable)
 *   |--- kvstore: a library for interacting with KV store collections (retrieving and editing values)
 *   |--- Users: a library getting the list of users
 *   |--- Capabilities: a library for get the capabilities of users
 *   |--- KVLookupInfo: a library for getting information for KV collections
 *   |--- ImportModal: the modal for helping import files into the lookup
 *   |--- BackupListInput: a view for displaying and selecting a list of the lookup backups
 */

require.config({
    paths: {
		// Main components
		kv_store_field_editor: '../app/lookup_editor/js/views/KVStoreFieldEditor',
		transform_create_view: '../app/lookup_editor/js/views/LookupTransformCreateView',
		table_editor_view: '../app/lookup_editor/js/views/TableEditorView',
		kvstore: '../app/lookup_editor/js/contrib/kvstore',
		capabilities: '../app/lookup_editor/js/utils/Capabilities',
		users: '../app/lookup_editor/js/utils/Users',
		kv_lookup_info: '../app/lookup_editor/js/utils/KVLookupInfo',
		import_modal: '../app/lookup_editor/js/views/ImportModal',
		backups_list_input: '../app/lookup_editor/js/views/BackupListInput',

		// Helper libraries
        text: '../app/lookup_editor/js/lib/text',
        console: '../app/lookup_editor/js/lib/console',
        csv: '../app/lookup_editor/js/lib/csv',
        clippy: '../app/lookup_editor/js/lib/clippy'
		
    },
    shim: {
        'clippy': {
            deps: ['jquery'],
            exports: 'clippy'
        }
    }
});

define([
    "underscore",
    "backbone",
    "models/SplunkDBase",
    "collections/SplunkDsBase",
    "splunkjs/mvc",
    "util/splunkd_utils",
    "jquery",
    "table_editor_view",
    "splunkjs/mvc/simplesplunkview",
    "splunkjs/mvc/simpleform/input/text",
    "splunkjs/mvc/simpleform/input/dropdown",
    "splunkjs/mvc/simpleform/input/checkboxgroup",
    "text!../app/lookup_editor/js/templates/LookupEdit.html",
	"kv_store_field_editor",
	"transform_create_view",
	"kvstore",
	"capabilities",
	"users",
	"kv_lookup_info",
	"import_modal",
	"backups_list_input",
    "clippy",
    "csv",
	"bootstrap.dropdown",
	"bootstrap.tooltip",
    "splunk.util",
    "css!../app/lookup_editor/css/LookupEdit.css",
    "css!../app/lookup_editor/css/lib/clippy.css",
], function(
    _,
    Backbone,
    SplunkDBaseModel,
    SplunkDsBaseCollection,
    mvc,
    splunkd_utils,
    $,
    TableEditorView,
    SimpleSplunkView,
    TextInput,
    DropdownInput,
    CheckboxGroupInput,
    Template,
	KVStoreFieldEditor,
	LookupTransformCreateView,
	KVStore,
	Capabilities,
	Users,
	KVLookupInfo,
	ImportModal,
	BackupListInput
){
	var Apps = SplunkDsBaseCollection.extend({
	    url: "apps/local?count=-1&search=disabled%3D0",
	    initialize: function() {
	      SplunkDsBaseCollection.prototype.initialize.apply(this, arguments);
	    }
	});
	
    // Define the custom view class
    var LookupEditView = SimpleSplunkView.extend({
        className: "LookupEditView",
        
        /**
         * Initialize the class.
         */
        initialize: function() {
        	this.options = _.extend({}, this.defaults, this.options);
            
            // The information for the loaded lookup
            this.lookup = null;
            this.namespace = null;
            this.owner = null;
            this.lookup_type = null;
            
            this.agent = null; // This is for Clippy
			
			// These retain some classes that we may instantiate and use
			this.kv_store_fields_editor = null;
			this.lookup_transform_create_view = null;
			this.table_editor_view = null;
			this.import_modal = null;
			this.backups_list_input = null;

        	// Get the apps
        	this.apps = new Apps();
        	this.apps.on('reset', this.gotApps.bind(this), this);
        	
        	this.apps.fetch({
                success: function() {
                  console.info("Successfully retrieved the list of applications");
                },
                error: function() {
                  console.error("Unable to fetch the apps");
                }
            });
        	
        	this.is_new = true;
        	this.info_message_posted_time = null;
        	
        	setInterval(this.hideInfoMessageIfNecessary.bind(this), 1000);
        	
        	// Listen to changes in the KV field editor so that the validation can be refreshed
			this.listenTo(Backbone, "kv_field:changed", this.validateForm.bind(this));
        },
        
        events: {
			"click #save"           : "doSaveLookup",
			"click #create"         : "doCreateLookup",
        	"click .user-context"   : "doLoadUserContext",
        	"click #export-file"    : "doExport",
        	"click #import-file"    : "openFileImportModal",
			"click #refresh"        : "refreshLookup",
			"click #edit-acl"       : "editACLs",
			"click #open-in-search" : "openInSearch",
			"keyup .search-lookup"  : "updateSearch"
        },
        
        /**
         * Hide the informational message if it is old enough
         */
        hideInfoMessageIfNecessary: function(){
        	if(this.info_message_posted_time && ((this.info_message_posted_time + 5000) < new Date().getTime() )){
        		this.info_message_posted_time = null;
        		$(".info-message", this.$el).fadeOut(200);
        	}
        },
        
        /**
         * Setup the drag-n-drop handler on the table.
         */
        setupDragDropHandlers: function(){
        	// Setup a handler for handling files dropped on the table
        	var drop_zone = document.getElementById('lookup-table');
        	this.import_modal.setupDragDropHandlerOnElement(drop_zone);
        },
        
        /**
         * Open the modal for importing a file.
         */
        openFileImportModal: function(){
			this.import_modal.show(this.lookup_type);
        },
        
        /**
         * Load the selected lookup from the history.
         * 
         * @param version The version of the lookup file to load (a value of null will load the latest version)
         */
        loadBackupFile: function(version){
			if(this.agent){
				this.agent.play("Processing");
			}
        	this.loadLookupContents(this.lookup, this.namespace, this.owner, this.lookup_type, false, version);
        },
        
        /**
         * Load the selected lookup from the given user's context.
         * 
         * @param user The user context from which to load the lookup
         */
        loadUserKVEntries: function(user){
        	// Stop if user wasn't provided
        	if( typeof user == 'undefined' ){
        		return;
        	}
        	
        	this.loadLookupContents(this.lookup, this.namespace, user, this.lookup_type, false);
        	
        	// Make a dict with arguments
        	var d = {
        		'owner' : user,
        		'namespace' : this.namespace,
        		'type' : this.lookup_type,
        		'lookup' : this.lookup,
        	};
        	
        	history.pushState(d, "Lookup Edit", "?" + $.param(d, true));
        },
        
        /**
         * Hide the warning message.
         */
        hideWarningMessage: function(){
        	this.hide($(".warning-message", this.$el));
        },
        
        /**
         * Hide the informational message
         */
        hideInfoMessage: function(){
        	this.hide($(".info-message", this.$el));
        },
        
        /**
         * Hide the messages.
         */
        hideMessages: function(){
        	this.hideWarningMessage();
        	this.hideInfoMessage();
        },
        
        /**
         * Show a warning noting that something bad happened.
		 * 
		 * @param message The message to show
         */
        showWarningMessage: function(message){
        	$(".warning-message > .message", this.$el).text(message);
        	this.unhide($(".warning-message", this.$el));
        },
        
        /**
         * Show a warning noting that something bad happened.
		 * 
		 * @param message The message to show
         */
        showInfoMessage: function(message){
        	$(".info-message > .message", this.$el).text(message);
        	this.unhide($(".info-message", this.$el));
        	
        	this.info_message_posted_time = new Date().getTime();
        },

	     /* 
	      * Cancel an import that is in-progress.
	      */
	     cancelImport: function(){
			this.cancel_import = true;
		 },

		 /**
		  * Import the daat into the KV store.
		  * 
		  * @param data The data to import (an array of arrays)
		  * @param offset An integer indicating the row to import
		  * @param promise A promise to resolve or reject when done
		  */
		 importKVRow: function(data, offset, promise){
			// Get a promise ready
			if(typeof promise === 'undefined'){
				promise = jQuery.Deferred();
			}

			// Update the progress bar
			this.import_modal.setProgress(data.length, this.import_successes, this.import_errors);

			// Stop if we hit the end (the base case)
			if(offset >= data.length || this.cancel_import){
				this.import_modal.hide();
				promise.resolve();
				return;
			}

			// Grab the next row
			var row = data[offset];

			var model_data = {};

			for(var c = 0; c < row.length; c++){
				// TODO convert formats as necessary; see makeRowJSON
				// Match up the format
				if(data[0][c] !== '_key'){
					model_data[data[0][c]] = row[c];
				}
			}

			var model = new this.kvStoreModel(model_data);

	        // Save the model
	        model.save()
				.done(function(){
					this.import_successes = this.import_successes + 1;
					this.importKVRow(data, offset+1, promise);
	        	}.bind(this))
				.error(function(){
					this.import_errors = this.import_errors + 1;
					this.importKVRow(data, offset+1, promise);
				}.bind(this));

			// Return the promise
			return promise;
		 },

		 /**
          * Import the given file into the KV store lookup.
		  *
		  * @param data The data to import
          */
		 importKVFile: function(data){
			// Make a promise
			var promise = jQuery.Deferred();

			// Clear the cancel indicator
			this.cancel_import = false;
			this.import_errors = 0;
			this.import_successes = 0;

			// Stop if the file has no rows
			if(data.length === 0){
				this.showWarningMessage("Unable to import the file since it has no rows");
				promise.reject();
				return promise;
			}

			// Verify that the input file matches the KV store collection
			// A file can only be imported if the import file has all of the columns of the schema (no gaps)
			var fields = _.keys(this.table_editor_view.getFieldTypes());
			var field = null;

			for(var c = 0; c < fields.length; c++){
				field = fields[c];

				// See if the field exists in the input file
				if(field !== "undefined"){

					var field_found = false;

					for(var d = 0; d < data[0].length; d++){
						if(data[0][d] === field){
							field_found = true;
						}
					}

					// Stop if the field could not be found
					if(!field_found){
						this.showWarningMessage("Unable to import the file since the input file is missing the column: " + field);
						promise.reject();
						return promise;
					}
				}
			}

			// Open the import modal
			this.import_modal.show(this.lookup_type);

			// Start the importation
			this.importKVRow(data, 1).done(function(){
				promise.resolve();
				this.refreshLookup();

				// Note a warning if some import errors exist
				if(this.import_errors > 0){
					this.showWarningMessage("Some rows (" + this.import_errors + ") could not be imported; make sure the values are of the correct type");
				}

			}.bind(this));

			// Return the promise
			return promise;
		 },

         /**
          * Import the given file into the lookup.
		  *
		  * @param evt The event for handling file imports
          */
         importFile: function(evt){
        	// Stop if this is read-only
        	if(this.table_editor_view.isReadOnly()){
        		console.info("Drag and dropping on a read-only lookup being ignored");
        		return false;
        	}
        	
        	// Stop if the browser doesn't support processing files in Javascript
        	if(!window.FileReader){
        		alert("Your browser doesn't support file reading in Javascript; thus, I cannot parse your uploaded file");
        		return false;
        	}
        	
        	// Get a reader so that we can read in the file
        	var reader = new FileReader();
        	
        	// Setup an onload handler that will process the file
        	reader.onload = function(evt) {
        		
        		console.log("Running file reader onload handler");
        		
        		// Stop if the ready state isn't "loaded"
                if(evt.target.readyState != 2){
                	return;
                }
                
                // Stop if the file could not be processed
                if(evt.target.error) {
                	
                	// Hide the loading message
                	$(".table-loading-message").hide();
                	
                	// Show an error
                    this.showWarningMessage("Unable to import the file");
                    return;
                }
                
                // Get the file contents
                var filecontent = evt.target.result;
                
                // Import the file into the view
				var data = new CSV(filecontent, {}).parse();

				if(this.lookup_type === "kv"){
					data = this.importKVFile(data).done(function(){
						$('#import-file-modal', this.$el).modal('hide');
					});
				}
            	
				else{
					// Render the lookup file
					if(!this.table_editor_view.renderLookup(data)){
						this.showWarningMessage("Lookup could not be loaded");
					}
					
					// Hide the import dialog
					$('#import-file-modal', this.$el).modal('hide');
					
					// Show a message noting that the file was imported
					this.showInfoMessage("File imported successfully");
				}
            	
        	}.bind(this);
        	
        	var files = [];
        	
        	// Get the files from the file input widget if available
        	if(evt.target.files && evt.target.files.length > 0){
        		files = evt.target.files;
        	}
        	
        	// Get the files from the drag & drop if available
        	else if(evt.dataTransfer && evt.dataTransfer.files.length > 0){
        		files = evt.dataTransfer.files;
        	}
        	
            // Stop if no files where provided (user likely pressed cancel)
            if(files.length > 0 ){
        	    
        	    // Set the file name if this is a new file and a filename was not set yet
        	    if(this.is_new && (!mvc.Components.getInstance("lookup-name").val() || mvc.Components.getInstance("lookup-name").val().length <= 0)){
        	    	mvc.Components.getInstance("lookup-name").val(files[0].name);
        	    }
        	    
        	    // Start the process of processing file
        	    reader.readAsText(files[0]);
        	    
            	if(this.agent){
            		this.agent.play("Thinking");
            	}
            }
            else{
            	// Hide the loading message
            	$(".table-loading-message").hide();
            }
        	
        },
        
		/**
		 * Initialize a class for KV store editing.
		 */
		initializeKVStoreModel: function(){
            this.kvStoreModel = KVStore.Model.extend({
                collectionName: this.lookup,
                namespace: {
                    'owner' : this.owner,
					'app' : this.namespace
                }
            });
		},

        /**
         * Make a new KV store lookup
		 * 
		 * @param namespace The namespace of the file
		 * @param lookup_file The name of the lookup
		 * @param owner The owner of the file
         */
        makeKVStoreLookup: function(namespace, lookup_file, replicate, owner){
        	// Set a default value for the owner
        	if( typeof owner == 'undefined' ){
        		owner = 'nobody';
			}
			
        	// Set a default value for the replicate parameter
        	if( typeof replicate == 'undefined' ){
        		replicate = false;
        	}
        	
        	// Make the data that will be posted to the server
        	var data = {
        		"name": lookup_file
        	};
        	
        	// Perform the call
        	$.ajax({
        			url: splunkd_utils.fullpath(['/servicesNS', owner, namespace, 'storage/collections/config'].join('/')),
        			data: data,
        			type: 'POST',
        			
        			// On success, populate the table
        			success: function(data) {
        				console.info('KV store lookup file created');
        			  
        				// Remember the specs on the created file
        				this.lookup = lookup_file;
        				this.namespace = namespace;
        				this.owner = owner;
        				this.lookup_type = "kv";

						this.initializeKVStoreModel();
        				
        				this.kv_store_fields_editor.modifyKVStoreLookupSchema(this.namespace, this.lookup, 'nobody', replicate, function(){
        					this.showInfoMessage("Lookup created successfully");
        					document.location = "?lookup=" + lookup_file + "&owner=" + owner + "&type=kv&namespace=" + namespace;
        				}.bind(this));
        			  
        			}.bind(this),
        		  
        			// Handle cases where the file could not be found or the user did not have permissions
        			complete: function(jqXHR, textStatus){
        				if( jqXHR.status == 403){
        					console.info('Inadequate permissions');
        					this.showWarningMessage("You do not have permission to make a KV store collection", true);
        				}
        				else if( jqXHR.status == 409){
        					console.info('Lookup name already exists');
        					$('#lookup-name-control-group', this.$el).addClass('error');
        	        		this.showWarningMessage("Lookup name already exists, please select another");
        				}
        				
        				this.setSaveButtonTitle();
        			  
        			}.bind(this),
        		  
        			// Handle errors
        			error: function(jqXHR, textStatus, errorThrown){
        				if( jqXHR.status != 403 && jqXHR.status != 409 ){
        					console.info('KV store collection creation failed');
        					this.showWarningMessage("The KV store collection could not be created", true);
        				}
        			}.bind(this)
        	});
        	
        },
        
        /**
         * Load the lookup file contents from the server and populate the editor.
         * 
         * @param lookup_file The name of the lookup file
         * @param namespace The app where the lookup file exists
         * @param user The user that owns the file (in the case of user-based lookups)
         * @param lookup_type Indicates whether this is a KV store or a CSV lookup (needs to be either "kv" or "csv")
         * @param header_only Indicates if only the header row should be retrieved
         * @param version The version to get from the archived history
         */
        loadLookupContents: function(lookup_file, namespace, user, lookup_type, header_only, version){

        	// Set a default value for header_only
        	if( typeof header_only === 'undefined' ){
        		header_only = false;
        	}
        	
        	var data = {"lookup_file":lookup_file,
                    	"namespace"  :namespace,
                    	"header_only":header_only,
                    	"lookup_type":lookup_type};
        	
        	// Set a default value for version
        	if( typeof version == 'undefined' ){
        		version = undefined;
        	}
        	
        	// Show the loading message
        	$(".table-loading-message").show(); // TODO replace
        	
        	// Set the version parameter if we are asking for an old version
        	if( version !== undefined && version ){
        		data.version = version;
        	}
        	
        	// If a user was defined, then pass the name as a parameter
        	if(user !== null){
        		data.owner = user;
        	}
        	
        	// Make the URL
			url = Splunk.util.make_full_url("/splunkd/__raw/services/data/lookup_edit/lookup_contents", data);
        	
        	// Started recording the time so that we figure out how long it took to load the lookup file
        	var populateStart = new Date().getTime();
        	
        	// Perform the call
        	$.ajax({
				url: url,
				cache: false,

				// On success, populate the table
				success: function (data) {

					// Data could not be loaded
					if (data === null) {
						console.error('JSON of lookup table could not be loaded (got an empty value)');
						this.showWarningMessage("The requested lookup file could not be loaded", true);
						$('.show-when-editing', this.$el).hide();
					}

					// Data can be loaded
					else {

						// Note that the lookup is empty
						if (data.length === 0) {
							console.error('JSON of lookup table was successfully loaded (though the file is blank)');
							this.showWarningMessage("The lookup is blank; edit it to populate it", true);
							this.table_editor_view.renderLookup(this.getDefaultData());
						}
						else {
							console.info('JSON of lookup table was successfully loaded');
							if (!this.table_editor_view.renderLookup(data)) {
								this.showWarningMessage("Lookup could not be loaded");
							}
						}

						var elapsed = new Date().getTime() - populateStart;
						console.info("Lookup loaded and rendered in " + elapsed + "ms");

						// Remember the specs on the loaded file
						this.lookup = lookup_file;
						this.namespace = namespace;
						this.owner = user;
						this.lookup_type = lookup_type;

						this.initializeKVStoreModel();

						// Update the UI to note which user context is loaded
						$('#loaded-user-context').text(this.owner);
					}

        		  }.bind(this),
        		  
        		  // Handle cases where the file could not be found or the user did not have permissions
        		  complete: function(jqXHR, textStatus){
        			  if(jqXHR.status == 404){
        				  console.info('Lookup file was not found');
        				  this.showWarningMessage("The requested lookup file does not exist", true);
						  $('.show-when-editing', this.$el).hide();
        			  }
        			  else if(jqXHR.status == 403){
        				  console.info('Inadequate permissions');
        				  this.showWarningMessage("You do not have permission to view this lookup file", true);
						  $('.show-when-editing', this.$el).hide();
        			  }
        			  else if(jqXHR.status == 420){
        				  console.info('File is too large');
        				  this.showWarningMessage("The file is too big to be edited (must be less than 10 MB)");
						  $('.show-when-editing', this.$el).hide();
        			  }
        			  
        			  // Hide the loading message
        			  $(".table-loading-message").hide();
        			  
        			  // Start the loading of the history
        			  if( version === undefined && this.lookup_type === "csv" ){
        				  this.backups_list_input.loadLookupBackupsList(lookup_file, namespace, user);
        			  }
        			  else if(this.lookup_type === "csv" && jqXHR.status === 200){
        				  // Show a message noting that the backup was imported
        				  this.showInfoMessage("Backup file was loaded successfully");
        			  }
        			  
        		  }.bind(this),
        		  
        		  // Handle errors
        		  error: function(jqXHR, textStatus, errorThrown){
        			  if( jqXHR.status != 404 && jqXHR.status != 403 && jqXHR.status != 420 ){
        				  console.info('Lookup file could not be loaded');
        				  this.showWarningMessage("The lookup could not be loaded from the server", true);
        			  }
        			  
    				  this.table_editor_view.setReadOnly(true);
    				  this.hideEditingControls();
        		  }.bind(this)
        	});
        },
        
        /**
         * Hide the editing controls
		 * 
		 * @param hide A boolean indicating that the controls should be hidden or shown
         */
        hideEditingControls: function(hide){
        	// Load a default for the version
        	if( typeof hide === 'undefined' ){
        		hide = true;
        	}
        	
        	if(hide){
        		$('.btn', this.$el).hide();
        	}
        	else{
        		$('.btn', this.$el).show();
        	}
        	
        },
        
        /**
         * Validate the content of the form for creating a lookup.
         */
        validateForm: function(){
        	var issues = 0;
        	
        	// By default assume everything passes
        	$('#lookup-name-control-group', this.$el).removeClass('error');
        	$('#lookup-app-control-group', this.$el).removeClass('error');
        	
        	this.hideWarningMessage();
        	
        	// Make sure the lookup name is defined
        	if(this.is_new && (!mvc.Components.getInstance("lookup-name").val() || mvc.Components.getInstance("lookup-name").val().length <= 0)){
        		$('#lookup-name-control-group', this.$el).addClass('error');
        		this.showWarningMessage("Please enter a lookup name");
        		issues = issues + 1;
			}
			
        	// Make sure the lookup name doesn't include spaces (https://lukemurphey.net/issues/2035)
        	else if(this.is_new && mvc.Components.getInstance("lookup-name").val().match(/ /gi)){
        		$('#lookup-name-control-group', this.$el).addClass('error');
        		this.showWarningMessage("Lookup name cannot contain spaces");
        		issues = issues + 1;
        	}

        	// Make sure the lookup name is acceptable
        	else if(this.is_new && !mvc.Components.getInstance("lookup-name").val().match(/^[-A-Z0-9_ ]+([.][-A-Z0-9_ ]+)*$/gi)){
        		$('#lookup-name-control-group', this.$el).addClass('error');
        		this.showWarningMessage("Lookup name is invalid");
        		issues = issues + 1;
        	}
        	
        	// Make sure the lookup app is defined
        	if(this.is_new && (! mvc.Components.getInstance("lookup-app").val() || mvc.Components.getInstance("lookup-app").val().length <= 0)){
        		$('#lookup-app-control-group', this.$el).addClass('error');
        		this.showWarningMessage("Select the app where the lookup will go");
        		issues = issues + 1;
        	}
        	
        	// Make sure at least one field is defined (for KV store lookups only)
        	if(this.is_new && this.lookup_type === "kv" ){
        		
        		var validate_response = this.kv_store_fields_editor.validate();
        		
        		if(validate_response !== true){
            		this.showWarningMessage(validate_response);
            		issues = issues + 1;
        		}
        	}
        	
        	// Determine if the validation passed
        	if(issues > 0){
        		return false;
        	}
        	else{
        		return true;
        	}
        },
        
        /**
         * Get the list of apps as choices.
         */
        getAppsChoices: function(){
        	// If we don't have the apps yet, then just return an empty list for now
        	if(!this.apps){
        		return [];
        	}
        	
        	var choices = [];
        	
        	for(var c = 0; c < this.apps.models.length; c++){
        		choices.push({
        			'label': this.apps.models[c].entry.associated.content.attributes.label,
        			'value': this.apps.models[c].entry.attributes.name
        		});
        	}
        	
        	return choices;
        	
        },
        
        /**
         * Get the apps
         */
        gotApps: function(){
        	// Update the list
        	if(mvc.Components.getInstance("lookup-app")){
        		mvc.Components.getInstance("lookup-app").settings.set("choices", this.getAppsChoices());
        	}
        	
        },
        
        /**
         * Set the title of the save button
		 * 
		 * @param title The title of the save button
         */
        setSaveButtonTitle: function(title){
        	if(typeof title == 'undefined' ){
				$("#save").addClass("custom-title");
        		$("#save").text("Save Lookup");
        	}
        	else{
				$("#save").removeClass("custom-title");
        		$("#save").text(title);
        	}
		},
		
        /**
         * Set the title of the create lookup button
		 * 
		 * @param title The title of the create button
         */
        setCreateButtonTitle: function(title){
        	if(typeof title == 'undefined' ){
        		$("#create").text("Create Lookup");
        	}
        	else{
        		$("#create").text(title);
        	}
        },
        
        /**
         * Pad an integer with zeroes.
		 * 
		 * @param num The number to pad
		 * @param size How many characters to pad it with
         */
        pad: function(num, size) {
            var s = num+"";
            while (s.length < size) s = "0" + s;
            return s;
        },
        
        /**
         * Update the modification time
         */
        updateTimeModified: function(){
        	var today = new Date();
        	
        	var am_or_pm = today.getHours() > 12 ? "PM" : "AM";
        	
        	$("#modification-time").text("Modified: " + today.getFullYear() + "/" + this.pad(today.getMonth() + 1, 2) + "/" + today.getDate() + " " + this.pad((today.getHours() % 12),2) + ":" + this.pad(today.getMinutes(), 2) + ":" + this.pad(today.getSeconds(),2) + " " + am_or_pm);
        	
        	$(".mod-time-icon > i").show();
        	$(".mod-time-icon > i").fadeOut(1000);
        },
        
        /**
         * Load the lookup from the selected user context.
		 * 
		 * @param evt The event object
         */
        doLoadUserContext: function(evt){
        	var user = evt.currentTarget.dataset.user;
        	
        	if(user){
        		this.loadUserKVEntries(user);
        		
        		if(this.agent){
            		this.agent.play("Processing");
            	}
        	}
        	
        },
        
        /**
         * Perform an export of the given file.
         */
        doExport: function(){
			var href= "../../../splunkd/__raw/services/data/lookup_edit/lookup_as_file?namespace=" + this.namespace + "&owner=" + this.owner + "&lookup_file=" + this.lookup + "&lookup_type=" + this.lookup_type;
			document.location = href;
        },
		
		/**
         * Perform the operation to create a new KV store lookup.
         * 
		 * @param evt The event object
         * @returns {Boolean}
         */
		doCreateLookup: function(evt){
        	// Change the title
        	this.setCreateButtonTitle("Saving...");
        	
        	if(this.agent){
        		this.agent.play("Save");
			}

        	// Started recording the time so that we figure out how long it took to save the lookup file
        	var populateStart = new Date().getTime();
        	
        	// Hide the warnings. We will repost them if the input is still invalid
        	this.hideMessages();
        	
        	// Stop if the form didn't validate
        	if(!this.validateForm()){
        		this.setCreateButtonTitle();
        		return;
        	}
			
			// Determine if we are to replicate the lookup
			var replicate = false;
			if($.inArray('replicate', mvc.Components.getInstance("lookup-replicate").val()) >= 0){
				replicate = true;
			}

        	// Make the lookup
        	this.makeKVStoreLookup(mvc.Components.getInstance("lookup-app").val(), mvc.Components.getInstance("lookup-name").val(), replicate);
		},

        /**
         * Perform the operation to save the lookup.
         * 
		 * @param evt The event object
         * @returns {Boolean}
         */
        doSaveLookup: function(evt){        	
        	// Change the title
        	this.setSaveButtonTitle("Saving...");
        	
        	if(this.agent){
        		this.agent.play("Save");
        	}
        	
        	// Started recording the time so that we figure out how long it took to save the lookup file
        	var populateStart = new Date().getTime();
        	
        	// Hide the warnings. We will repost them if the input is still invalid
        	this.hideMessages();
		
			// Get the row data
			row_data = this.table_editor_view.getData();
			header_row_data = this.table_editor_view.getTableHeader(false);
			row_data.unshift(header_row_data);
			
			// Convert the data to JSON
			json = JSON.stringify(row_data);
			
			// Make the arguments
			var data = {
					lookup_file : this.lookup,
					namespace   : this.namespace,
					contents    : json
			};
			
			// If a user was defined, then pass the name as a parameter
			if(this.owner !== null){
				data.owner = this.owner;
			}
			
			// Validate the input if it is a new CSV lookup
			if(this.is_new){

				// Check the form
				if(!this.validateForm()){
					this.setSaveButtonTitle();
					return false;
				}
				
				// Get the lookup file name from the form if we are making a new lookup
				data.lookup_file = mvc.Components.getInstance("lookup-name").val();
					
				// Get the namespace from the form if we are making a new lookup
				data.namespace = mvc.Components.getInstance("lookup-app").val();
				
				// Set the owner if the user wants a user-specific lookup
				if($.inArray('user_only', mvc.Components.getInstance("lookup-user-only").val()) >= 0){
					data.owner = Splunk.util.getConfigValue("USERNAME");
				}
			}

			// Make sure at least a header exists; stop if not enough content is present
			if(row_data.length === 0){		
				this.showWarningMessage("Lookup files must contain at least one row (the header)");
				return false;
			}
			
			// Make sure the headers are not empty.
			// If the editor is allowed to add extra columns then ignore the last row since this for adding a new column thus is allowed
			for( i = 0; i < row_data[0].length; i++){
				
				// Determine if this row has an empty header cell
				if( row_data[0][i] === "" ){
					this.showWarningMessage("Header rows cannot contain empty cells (column " + (i + 1) + " of the header is empty)");
					return false;
				}
			}
			
			// Perform the request to save the lookups
			$.ajax( {
				url: Splunk.util.make_full_url("/splunkd/__raw/services/data/lookup_edit/lookup_contents"),
				type: 'POST',
				data: data,

				success: function () {
					console.log("Lookup file saved successfully");
					this.showInfoMessage("Lookup file saved successfully");
					this.setSaveButtonTitle();

					// Persist the information about the lookup
					if (this.is_new) {
						this.lookup = data.lookup_file;
						this.namespace = data.namespace;
						if(data.owner){
							this.owner = data.owner;
						}
						else{
							this.owner = 'nobody';
						}
						
						this.lookup_type = "csv";
					}
				}.bind(this),

				// Handle cases where the file could not be found or the user did not have permissions
				complete: function (jqXHR, textStatus) {
					var elapsed = new Date().getTime() - populateStart;
					console.info("Lookup save operation completed in " + elapsed + "ms");
					var success = true;

					if (jqXHR.status == 404) {
						console.info('Lookup file was not found');
						this.showWarningMessage("This lookup file could not be found");
						success = false;
					}
					else if (jqXHR.status == 403) {
						console.info('Inadequate permissions');
						this.showWarningMessage("You do not have permission to edit this lookup file");
						success = false;
					}
					else if (jqXHR.status == 400) {
						console.info('Invalid input');
						this.showWarningMessage("This lookup file could not be saved because the input is invalid");
						success = false;
					}
					else if (jqXHR.status == 500) {
						this.showWarningMessage("The lookup file could not be saved");
						success = false;
					}

					this.setSaveButtonTitle();

					// If we made a new lookup, then switch modes
					if (this.is_new && success) {
						this.changeToEditMode();
					}

					// Update the lookup backup list
					if (success) {
						this.backups_list_input.loadLookupBackupsList(this.lookup, this.namespace, this.owner);
					}
				}.bind(this),

				error: function (jqXHR, textStatus, errorThrown) {
					console.log("Lookup file not saved");
					this.showWarningMessage("Lookup file could not be saved");
				}.bind(this)
			});

        	return false;
        },
        
        /**
         * Do an edit to a row cell (for KV store lookups since edits are dynamic).
		 * 
		 * @param row The number of the row
		 * @param col The column number
		 * @param new_value The new value
         */
        doEditCell: function(row, col, new_value){
        	// Stop if we are in read-only mode
        	if(this.table_editor_view.isReadOnly()){
        		return;
        	}

        	// First, we need to get the _key of the edited row
			var row_data = this.table_editor_view.getDataAtRow(row);

			if(!row_data){
				this.showWarningMessage("Unable to find the row data for editing");
				return;
			}

			var col = this.table_editor_view.getColumnForField('_key');
        	var _key = row_data[col];

        	if(_key === undefined){
        		console.error("Unable to get the _key for editing the cell at (" + row + ", " + col + ")");
        		return;
        	}
        	
			// Second, we need to get all of the data from the given row because we must re-post all of the cell data
			try{
				var record_data = this.table_editor_view.makeRowJSON(row);
				this.hideWarningMessage();
			}
			catch(err){
				this.showWarningMessage(err);
				return;
			}

			if(_key !== null && _key !== undefined && _key.length > 0){
				record_data._key = _key;
			}

        	// Third, we need to do a post to update the row
            var model = new this.kvStoreModel(record_data);
			
            model.save({wait: true})
                .done(function(data) {
      		  		this.hideWarningMessage();
      		  		
      		  		// If this is a new row, then populate the _key
      		  		if(!_key){
      		  			_key = data._key;
      		  			this.table_editor_view.setDataAtCell(row, "_key", _key, "key_update");
      		  			console.info('KV store entry creation completed for entry ' + _key);
      		  		}
      		  		else{
      		  			console.info('KV store entry edit completed for entry ' + _key);
      		  		}
      		  		
      		  		this.updateTimeModified();
                }.bind(this))
				.error(function(jqXHR, result, message){
					// Detect cases where the user has inadequate permission
      		  		if(jqXHR !== null && jqXHR.status == 403){
      		  			console.info('Inadequate permissions');
      		  			this.showWarningMessage("You do not have permission to edit this lookup", true);
      		  		}

					// Detect type errors
					else if(jqXHR !== null && jqXHR.status == 400){
						this.showWarningMessage("Entry could not be saved to the KV store lookup; make sure the value matches the expected type", true);
					}

					// Output errors
					else if(message !== null){
						this.showWarningMessage("Entry could not be saved to the KV store lookup: " + message , true);
					}

					// Detect other errors
					else{
						this.showWarningMessage("Entry could not be saved to the KV store lookup;", true);
					}
				}.bind(this));
        },
		
        /**
         * Do the removal of a row (for KV store lookups since edits are dynamic).
		 * 
		 * @param row The row number
		 * @param row_data The row data
         */
        doRemoveRow: function(row, row_data){
        	// Stop if we are in read-only mode
        	if(this.table_editor_view.isReadOnly()){
        		return;
        	}
        	
			// First, we need to get the _key of the edited row
			if(!row_data) {
				row_data = this.table_editor_view.getDataAtRow(row);
			}

        	var _key = row_data[0];
        	
        	// Second, make sure the _key is valid
        	if(!_key && _key.length < 0){
        		console.error("Attempt to delete an entry without a valid key");
        		return false;
        	}
        	
        	// Third, we need to do a post to remove the row
            var model = new this.kvStoreModel({_key: _key});

            model.destroy({wait: true})
                .done(function() {
                        console.info('KV store entry removal completed for entry ' + _key);
                        this.hideWarningMessage();
                        this.updateTimeModified();
                }.bind(this))
				.error(function(jqXHR){

					// Detect cases where the user has inadequate permission
      		  		if( jqXHR.status == 403){
      		  			console.info('Inadequate permissions');
      		  			this.showWarningMessage("You do not have permission to edit this lookup", true);
      		  		}

					// Detect other errors
					else{
						this.showWarningMessage("An entry could not be removed from the KV store lookup", true);
					}
				}.bind(this));

			return true;
        },
        
        /**
         * Do the creation of a row (for KV store lookups since edits are dynamic).
		 * 
		 * @param row The row number to add to
		 * @param count The number of rows to add
         */
        doCreateRows: function(row, count){
        	// Stop if we are in read-only mode
        	if(this.table_editor_view.isReadOnly()){
        		return;
        	}
        	
        	// Create entries for each row to create
        	var record_data = [];
        	
        	for(var c=0; c < count; c++){
        		record_data.push(this.table_editor_view.makeRowJSON(row + c));
        	}
        	
        	// Third, we need to do a post to create the row
            var model = new this.kvStoreModel(record_data);

            model.save({wait: true})
                .done(function(data) {
      		  		// Update the _key values in the cell
					this.table_editor_view.setDataAtCell(row, "_key", data._key, "key_update");
      		  		
      		  		this.hideWarningMessage();
      		  		this.updateTimeModified();
                }.bind(this))
				.error(function(jqXHR){

					// Detect cases where the user has inadequate permission
      		  		if(jqXHR.status == 403){
      		  			console.info('Inadequate permissions');
      		  			this.showWarningMessage("You do not have permission to edit this lookup", true);
      		  		}

					// Detect other errors
					else{
      		  			// This error can be thrown when the lookup requires a particular type
      		  			//this.showWarningMessage("Entries could not be saved to the KV store lookup", true);
					}
				}.bind(this));
        },
        
        /**
         * Hide the given item while retaining the display value
		 * 
		 * @param selector A jQuery selector of the element to process
         */
        hide: function(selector){
        	selector.css("display", "none");
        	selector.addClass("hide");
        },
        
        /**
         * Un-hide the given item.
         * 
         * Note: this removes all custom styles applied directly to the element.
		 * 
		 * @param selector A jQuery selector of the element to process
         */
        unhide: function(selector){
        	selector.removeClass("hide");
        	selector.removeAttr("style");
        },
        
        /**
         * Change from the new mode of the editor to the edit mode
         */
        changeToEditMode: function(){
        	// Hide the creation controls
			this.hide($('.show-when-creating', this.$el));
			this.unhide($('.show-when-editing', this.$el));
        	
        	// Change the title
        	$('h2.lookup-name', this.$el).text("/ " + this.lookup);
        	
        	// Remember that we are not editing a file
			this.is_new = false;
			
			// Change the URL
			var url = "?lookup=" + this.lookup + "&namespace=" + this.namespace + "&type=" + this.lookup_type;
			
			if(this.owner){
				url += "&owner=" + this.owner;
			}
			else{
				url += "&owner=nobody";
			}
			
			history.pushState(null, "Lookup Edit", url);
        },
        
        /**
         * Handle shortcut key-presses.
         */
        handleShortcuts: function(e){
        	if (e.keyCode == 69 && e.ctrlKey) {
                this.toggleClippy();
            }
        },
        
        /**
         * Turn clippy on or off.
         */
        toggleClippy: function(){
        	// Make the clippy instance if necessary
        	if(this.agent === null){
            	clippy.load('Clippy', function(agent) {
                    this.agent = agent;
                    this.agent.show();
                }.bind(this));
        	}
        	
        	// Show clippy if he was made but is hidden
        	else if($(".clippy").length === 0 || !$(".clippy").is(":visible")){
        		this.agent.show();
        	}
        	
        	// Hide clippy if he was made and is shown
        	else if($(".clippy").length > 0 && $(".clippy").is(":visible")){
        		this.agent.hide();
        	}
        },
        
        /**
         * Get a default table.
         */
        getDefaultData: function(){
        	return [
    		            ["Column1", "Column2", "Column3", "Column4", "Column5", "Column6"],
    		            ["", "", "", "", "", ""],
    		            ["", "", "", "", "", ""],
    		            ["", "", "", "", "", ""],
    		            ["", "", "", "", "", ""]
    		          ];
        },

		/**
		 * Edit the ACLs.
		 */
		editACLs: function(){
			var uri = null;

			if(this.lookup_type == 'kv'){
				uri = Splunk.util.make_url('/splunkd/__raw/servicesNS/nobody/' + this.namespace + '/storage/collections/config/' + this.lookup);
				document.location = Splunk.util.make_url('/manager/permissions/' + this.namespace + '/storage/collections/config/' + this.lookup + '?uri=' + encodeURIComponent(uri));
			}
			else{
				uri = Splunk.util.make_url('/splunkd/__raw/servicesNS/' + this.owner + '/' + this.namespace + '/data/lookup-table-files/' + this.lookup);
				document.location = Splunk.util.make_url('/manager/permissions/' + this.namespace + '/data/lookup-table-files/' + this.lookup + '?uri=' + encodeURIComponent(uri));
			}

		},

		/**
		 * Open the lookup in search or create a transform so that it can be searched.
		 */
		openInSearch: function(){
			// Make the lookup transform view if necessary
			if(this.lookup_transform_create_view === null){
				this.lookup_transform_create_view = new LookupTransformCreateView({
					el: $('#lookup-transform-modal')
				});

				$.when(this.lookup_transform_create_view.render()).done(function(){
					this.lookup_transform_create_view.openInSearchOrCreateTransform(this.owner, this.namespace, this.lookup);
				}.bind(this));

			// Otherwise, just show the existing form
			} else {
				this.lookup_transform_create_view.openInSearchOrCreateTransform(this.owner, this.namespace, this.lookup);
			}
			
		},

		/**
		 * Perform a search.
		 */
		updateSearch: function(){
			this.table_editor_view.search($('.search-lookup').val());
		},

		/**
		 * Refresh the lookup.
		 */
		refreshLookup: function(){
			this.loadLookupContents(this.lookup, this.namespace, this.owner, this.lookup_type);
		},

        /**
         * Render the page.
         */
        render: function () {
			$.when(Capabilities.hasCapability('admin_all_objects')).done(function(has_permission){
				// Get the information from the lookup to load
				this.lookup = decodeURIComponent(Splunk.util.getParameter("lookup"));
				this.namespace = decodeURIComponent(Splunk.util.getParameter("namespace"));

				if(Splunk.util.getParameter("owner")){
					this.owner = decodeURIComponent(Splunk.util.getParameter("owner"));
				}
				else{
					this.owner = null;
				}

				this.lookup_type = decodeURIComponent(Splunk.util.getParameter("type"));
				
				// Determine if we are making a new lookup
				this.is_new = false;
				
				if((this.lookup === null && this.namespace === null && this.owner === null) || (Splunk.util.getParameter("action") === "new")){
					this.is_new = true;
				}
				
				// Make an open in search link
				var search_link = null;
				if(this.lookup_type === 'csv'){
					search_link = LookupTransformCreateView.prototype.makeSearchLink(this.lookup);
				}

				// Make descriptions for the special users
				var user_descriptions = {
					nobody : 'entries visible from search'
				};

				user_descriptions[this.owner] = 'owner of the lookup';

				var default_users = [
					{
						'name' : 'nobody',
						'readable_name' : 'nobody',
						'description' : 'entries visible from search'
					},
					{
						'name' : Splunk.util.getConfigValue("USERNAME"),
						'readable_name' : Splunk.util.getConfigValue("USERNAME"),
						'description' : ''
					},
				];

				// Get a list of users to show from which to load the context
				$.when(Users.getUsers(this.owner, user_descriptions, default_users)).done(function(users){
					// Sort the users list
					users = Users.sortUsersList(users, ['nobody', this.owner, Splunk.util.getConfigValue("USERNAME")]);
					
					var insufficient_permissions = !has_permission && this.is_new && this.lookup_type === "kv";

					// Render the HTML content
					this.$el.html(_.template(Template, {
						'insufficient_permissions' : insufficient_permissions,
						'is_new' : this.is_new,
						'lookup_name': this.lookup,
						'lookup_type' : this.lookup_type,
						'users' : users,
						'search_link' : search_link
					}));

					// Initialize the table editor if we haven't already
					if(this.table_editor_view === null){
						this.table_editor_view = new TableEditorView({
							el: '#lookup-table',
							lookup_type: this.lookup_type
						});

						// Wire up the handlers
						this.table_editor_view.on("editCell", function(data) {
							this.doEditCell(data.row, data.col, data.new_value);
						}.bind(this));

						this.table_editor_view.on("removeRow", function(row) {
							this.doRemoveRow(row);
						}.bind(this));

						this.table_editor_view.on("createRows", function(data) {
							// Don't create empty rows in the KV store, wait until values are provided
							// this.doCreateRows(data.row, data.count);
						}.bind(this));
						
					}
					
					// Setup a handler for the shortcuts
					$(document).keydown(this.handleShortcuts.bind(this));
					console.info("Press CTRL + E to see something interesting");

					// Show the content that is specific to making new lookups
					if (!insufficient_permissions && this.is_new) {

						// Make the lookup name input
						var name_input = new TextInput({
							"id": "lookup-name",
							"searchWhenChanged": false,
							"el": $('#lookup-name', this.$el)
						}, { tokens: true }).render();

						name_input.on("change", function (newValue) {
							this.validateForm();
						}.bind(this));

						// Make the app selection drop-down
						var app_dropdown = new DropdownInput({
							"id": "lookup-app",
							"selectFirstChoice": false,
							"showClearButton": false,
							"el": $('#lookup-app', this.$el),
							"choices": this.getAppsChoices()
						}, { tokens: true }).render();

						app_dropdown.on("change", function (newValue) {
							this.validateForm();
						}.bind(this));

						// Make the user-only lookup checkbox
						var user_only_checkbox = new CheckboxGroupInput({
							"id": "lookup-user-only",
							"choices": [{ label: "User-only", value: "user_only" }],
							"el": $('#lookup-user-only')
						}, { tokens: true }).render();

						user_only_checkbox.on("change", function (newValue) {
							this.validateForm();
						}.bind(this));

						// Make the replicate lookup checkbox
						var replicate_checkbox = new CheckboxGroupInput({
							"id": "lookup-replicate",
							"choices": [{ label: "Replicate", value: "replicate" }],
							"el": $('#lookup-replicate')
						}, { tokens: true }).render();

						replicate_checkbox.on("change", function (newValue) {
							this.validateForm();
						}.bind(this));

					}

					// Make the import modal
					if(this.import_modal === null){
						this.import_modal = new ImportModal({
							el: '#import-modal'
						});

						this.listenTo(this.import_modal, 'cancelImport', this.cancelImport.bind(this));
						this.listenTo(this.import_modal, 'startImport', this.importFile.bind(this));
					}

					// Setup the handlers so that we can make the view support drag and drop
					this.setupDragDropHandlers();

					// Make the backups list input
					if(this.backups_list_input === null){
						this.backups_list_input = new BackupListInput({
							el: '#backup-list'
						});

						this.backups_list_input.render();

						this.listenTo(this.backups_list_input, 'loadBackup', this.loadBackupFile.bind(this));
					}

					// If we are editing an existing KV lookup, then get the information about the lookup and _then_ get the lookup data
					if (this.lookup_type === "kv" && !this.is_new) {
						$.when(KVLookupInfo.getInfo(this.namespace, this.lookup))
						.done(function(field_types, field_types_enforced, read_only){
							// Configure the table editor
							this.table_editor_view.setFieldTypes(field_types);
							this.table_editor_view.setFieldTypeEnforcement(field_types_enforced);
							this.table_editor_view.setReadOnly(read_only);

							if(read_only){
								this.showWarningMessage("You do not have permission to edit this lookup; it is being displayed read-only");
							}

							// Load the lookup
							this.loadLookupContents(this.lookup, this.namespace, this.owner, this.lookup_type);
						}.bind(this))
						.fail(function(){
							console.warn("Unable to retrieve the information about the KV store lookup");
						}.bind(this));
					}

					// If we are making an new KV lookup, then show the form that allows the user to define the meta-data
					else if (this.lookup_type === "kv" && this.is_new) {
						this.kv_store_fields_editor = new KVStoreFieldEditor({
							'el': $('#lookup-kv-store-edit', this.$el)
						});

						this.kv_store_fields_editor.render();
		
						// Render the tooltip for the replication option
						$('[data-toggle="tooltip"]').tooltip();

						$('#lookup-kv-store-edit', this.$el).show();
						$('#save', this.$el).show();
						$('.editing-content', this.$el).hide();
					}

					// If this is a new lookup, then show default content accordingly
					else if (this.is_new) {
						// Show a default lookup if this is a new lookup
						this.table_editor_view.renderLookup(this.getDefaultData());
					}

					// Stop if we didn't get enough information to load a lookup
					else if (this.lookup === null || this.namespace === null || this.owner === null) {
						this.showWarningMessage("Not enough information to identify the lookup file to load");
					}

					// Otherwise, load the lookup
					else {
						this.loadLookupContents(this.lookup, this.namespace, this.owner, this.lookup_type);
					}
				}.bind(this));
			}.bind(this));
		}
    });
    
    return LookupEditView;
});