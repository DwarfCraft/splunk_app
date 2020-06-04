
require.config({
    paths: {
        datatables: "../app/lookup_editor/js/lib/DataTables/js/jquery.dataTables",
		bootstrapDataTables: "../app/lookup_editor/js/lib/DataTables/js/dataTables.bootstrap",
		lookupTransformCreateView: "../app/lookup_editor/js/views/LookupTransformCreateView",
		modalDialog: "../app/lookup_editor/js/views/ModalDialog",
        text: "../app/lookup_editor/js/lib/text",
        console: '../app/lookup_editor/js/lib/console'
    },
    shim: {
        'bootstrapDataTables': {
            deps: ['datatables']
        }
    }
});

define([
    "underscore",
    "backbone",
    "models/SplunkDBase",
    "collections/SplunkDsBase",
    "splunkjs/mvc",
    "jquery",
    "splunkjs/mvc/simplesplunkview",
    "text!../app/lookup_editor/js/templates/LookupList.html",
	"bootstrapDataTables",
	"lookupTransformCreateView",
	"modalDialog",
    "util/splunkd_utils",
    "bootstrap.dropdown",
    "css!../app/lookup_editor/css/LookupList.css",
    "css!../app/lookup_editor/css/SplunkDataTables.css"
], function(
    _,
    Backbone,
    SplunkDBaseModel,
    SplunkDsBaseCollection,
    mvc,
    $,
    SimpleSplunkView,
    Template,
	dataTable,
	LookupTransformCreateView,
	ModalDialog,
    splunkd_utils
){
	
	var Apps = SplunkDsBaseCollection.extend({
	    url: "apps/local?count=-1",
	    initialize: function() {
	      SplunkDsBaseCollection.prototype.initialize.apply(this, arguments);
	    }
	});
	
	var LookupTransforms = SplunkDsBaseCollection.extend({
	    url: "data/transforms/lookups?count=-1",
	    initialize: function() {
	      SplunkDsBaseCollection.prototype.initialize.apply(this, arguments);
	    }
	});
	
	var CSVLookup = SplunkDBaseModel.extend({
		url: "data/lookup-table-files",
		initialize: function() {
			SplunkDsBaseCollection.prototype.initialize.apply(this, arguments);
		}
	});

	var CSVLookups = SplunkDsBaseCollection.extend({
		url: Splunk.util.make_url('/splunkd/__raw/servicesNS', encodeURIComponent(Splunk.util.getConfigValue("USERNAME"))) + '/-/data/lookup-table-files?count=-1',
		model: CSVLookup,
		initialize: function() {
			SplunkDsBaseCollection.prototype.initialize.apply(this, arguments);
		}
	});

	var KVLookup = SplunkDBaseModel.extend({
		url: "storage/collections",
		initialize: function() {
			SplunkDsBaseCollection.prototype.initialize.apply(this, arguments);
		}
	});

	var KVLookups = SplunkDsBaseCollection.extend({
		url: Splunk.util.make_url('/splunkd/__raw/servicesNS/nobody/-/storage/collections/config?count=-1'),
		model: KVLookup,
	    initialize: function() {
	      SplunkDsBaseCollection.prototype.initialize.apply(this, arguments);
	    }
	});
	
    // Define the custom view class
    var LookupListView = SimpleSplunkView.extend({
        className: "LookupListView",

        events: {
        	// Filtering
        	"click .type-filter > .dropdown-menu > li > a" : "onClickTypeFilter",
        	"click .app-filter > .dropdown-menu > li > a" : "onClickAppFilter",
        	"click .scope-filter > .btn" : "onClickScopeFilter",
        	"change #free-text-filter" : "applyFilter",
        	"keyup #free-text-filter" : "goFilter",
        	"keypress #free-text-filter" : "goFilter",
        	
        	// Options for disabling lookups
        	"click .disable-kv-lookup" : "openDisableKVLookupDialog",
        		
            // Options for enabling lookups
			"click .enable-kv-lookup" : "enableLookup",
			
			// Open the lookup in search
			"click .open-in-search" : "openInSearch",

			// Options for delete
			"click .delete-lookup" : "confirmAndDeleteLookup"
        },

        defaults: {
        	change_dropdown_titles: true
        },
        
        /**
         * Initialize the class.
         */
        initialize: function() {
        	this.options = _.extend({}, this.defaults, this.options);
        	
        	// Save the options
        	this.change_dropdown_titles = this.options.change_dropdown_titles;
        	
            // Filtering options
            this.filter_app = null;
            this.filter_type = null;
            this.filter_scope = null;
            this.filter_text = null;
            
            // This tracks the filter that was applied
            this.applied_filter = null;
            
            // This stores the list of apps
            this.apps = null;
            
            // The reference to the data-table
            this.data_table = null;
            
            // This indicates if data-table's state should be retained
            this.retain_state = false;
        	
        	// Get the CSV lookups
			this.csv_lookups = null;
			this.getCSVLookups();
        	
        	// Get the KV store lookups
			this.kv_lookups_supported = true;
			this.kv_lookups = null;
        	this.getKVLookups();
        	
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
        	
        	// Get the lookup transforms
        	this.lookup_transforms = new LookupTransforms();
        	this.lookup_transforms.on('reset', this.gotLookupTransforms.bind(this), this);
        	
        	this.lookup_transforms.fetch({
                success: function() {
                  console.info("Successfully retrieved the list of lookup transforms");
                },
                error: function() {
                  console.error("Unable to fetch the lookup transforms");
                }
			});

			// Keep a reference around for the lookup transform editor
			this.lookup_transform_editor = null;

			// Below are the modals we will be using
			this.deleteModal = null;
			this.disableModal = null;
        },
		
		/**
		 * Get the CSV lookups
		 */
		getCSVLookups: function(retainState){
        	this.csv_lookups = new CSVLookups();
        	this.csv_lookups.on('reset', this.gotCSVLookups.bind(this), this);
        	
        	this.csv_lookups.fetch({
                success: function() {
                  console.info("Successfully retrieved the CSV lookup files");
                },
                error: function() {
                  console.error("Unable to fetch the CSV lookup files");
                }
            });
		},

        /**
         * Get the KV store lookups
         */
        getKVLookups: function(){
        	this.kv_lookups = new KVLookups();
        	this.kv_lookups.on('reset', this.gotKVLookups.bind(this), this);
        	
        	this.kv_lookups.fetch({
                success: function() {
                  console.info("Successfully retrieved the KV store lookup files");
                },
                error: function() {
                  console.error("Unable to fetch the KV store lookup files");
                },
                complete: function(jqXHR, textStatus){
                	if( jqXHR.status == 404){
                		
                		// The endpoint for KV store lookups doesn't exist; that's because this is a host that is too old to have KV store support
                		this.hideKVStoreOptions();
                		
                		this.kv_lookups_supported = false;
                	}
                }.bind(this)
            });
        },
        
        /**
         * Hide options for systems that do not support KV store (Splunk 6.2 and earlier)
         */
        hideKVStoreOptions: function(){
        	$(".show-kv-supported-only", this.$el).hide();
        	$(".show-kv-unsupported-only", this.$el).show();
        },
        
        /**
         * Set the name associated with the filter
         */
        setFilterText: function(filter_name, prefix, appendix){
        	
        	if (typeof appendix === "undefined") {
        		appendix = "All";
        	}
        	
    		if(this.change_dropdown_titles){
    			
    			if(appendix){
    				$("." + filter_name + " > .dropdown-toggle").html(prefix + ': ' + appendix + '<span class="caret"></span>');
    			}
    			else{
    				$("." + filter_name + " > .dropdown-toggle").html(prefix + '<span class="caret"></span>');
    			}
    			
    		}
        },
        
        /**
         * Perform the operation to perform a filter.
         */
        doFilter: function(filter_name, prefix, value, apply_filter){
        	
        	// Load a default for the apply_filter parameter
        	if( typeof apply_filter == 'undefined' ){
        		apply_filter = true;
        	}
        	
        	// Determine the value that should be checked
        	var valueToSet = value;
        	
        	if(value === null){
        		valueToSet = "All";
        	}
        	
        	// Set the text of the filter dropdown
        	this.setFilterText(filter_name, prefix, valueToSet);
        	
        	// Show the checked icon on the selected entry and only on that entry
        	$('.' + filter_name + ' > .dropdown-menu > li > a').each(function() {
        		if($(this).text() === valueToSet){
        			$("i", this).removeClass('hide');
        		}
        		else{
        			$("i", this).addClass('hide');
        		}
        	});
        	
        	// Apply the filter to the results
        	if(apply_filter){
        		this.applyFilter();
        	}
        	
        },
        
        /**
         * Apply the type filter on click.
         */
        onClickTypeFilter: function(ev){
        	var filter = $(ev.target).text();
        	this.setTypeFilter(filter);
        },
        
        /**
         * Set the type filter
         */
        setTypeFilter: function(filter){
        	
        	if(filter === "All"){
        		this.filter_type = null;
        	}
        	else{
        		this.filter_type = filter;
        	}
        	
        	// Execute the filter
        	this.doFilter('type-filter', 'Type', filter);
        	
        },
        
        /**
         * Apply the scope filter on click.
         */
        onClickScopeFilter: function(ev){
        	var filter = $(ev.target).text();
        	this.setScopeFilter(filter);
        },
		
		/**
		 * Escape a regular expression.
		 */
		escapeRegEx: function(string) {
			return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); // $& means the whole matched string
		},

        /**
         * Set the scope filter
         */
        setScopeFilter: function(filter){
        	
        	var filterText = "All";
        	
        	if(filter === "All" || filter === null){
        		this.filter_scope = null;
        	}
        	else if( filter.indexOf("Global") >= 0 ){
        		this.filter_scope = "nobody";
        		filterText = "Global";
        	}
        	else{
        		this.filter_scope = Splunk.util.getConfigValue("USERNAME");
        		filterText = "Mine";
        	}
        	
        	// Show the button as active on the selected entry and only on that entry
        	$('.scope-filter > .btn').each(function() {
        		if($(this).text() === filterText){
        			$(this).addClass('active');
        		}
        		else{
        			$(this).removeClass('active');
        		}
        	});
        	
        	this.applyFilter();
        	
        },
        
        /**
         * Apply the app filter on click.
         */
        onClickAppFilter: function(ev){
        	var filter = $(ev.target).text();
        	this.setAppFilter(filter);
        },
        
        /**
         * Set the app filter
         */
        setAppFilter: function(filter){
        	
        	if(filter === "All"){
        		this.filter_app = null;
        	}
        	else{
        		this.filter_app = filter;
        	}
        	
        	this.doFilter('app-filter', 'App', filter);
        	
        },
        
        /**
         * Enable the given lookup. 
         */
        enableLookup: function(ev){
        	
        	// Get the lookup that is being requested to enable
        	var lookup = $(ev.target).data("name");
        	var namespace = $(ev.target).data("namespace");
        	var owner = $(ev.target).data("owner");
        	
        	// Perform the call
        	$.ajax({
        			url: splunkd_utils.fullpath(['/servicesNS', "nobody", namespace, 'storage/collections/config', lookup, 'enable'].join('/')),
        			type: 'POST',
        			
        			// On success, populate the table
        			success: function() {
        				console.info('KV store lookup enabled');
        				
        			}.bind(this),
        		  
        			// Handle cases where the file could not be found or the user did not have permissions
        			complete: function(jqXHR, textStatus){
        				if( jqXHR.status == 403){
        					console.info('Inadequate permissions to enable collection');
        				}
        				else{
        					this.retain_state = true;
        					this.getKVLookups();
        				}
        				
        			}.bind(this),
        		  
        			// Handle errors
        			error: function(jqXHR, textStatus, errorThrown){
        				if( jqXHR.status != 403 ){
        					console.info('KV store collection enablement failed');
        				}
        			}.bind(this)
        	});
        	
        	return false;
        },
        
        /**
         * Disable the given lookup. 
         */
        disableLookup: function(lookup, namespace, owner){

        	// Perform the call
        	$.ajax({
        			url: splunkd_utils.fullpath(['/servicesNS', "nobody", namespace, 'storage/collections/config', lookup, 'disable'].join('/')),
        			type: 'POST',
        			
        			// On success
        			success: function() {
        				console.info('KV store lookup disabled');
        			}.bind(this),
        		  
        			// Handle cases where the file could not be found or the user did not have permissions
        			complete: function(jqXHR, textStatus){
        				if( jqXHR.status == 403){
        					console.info('Inadequate permissions to disable collection');
        				}
        				else{
        					$("#disable-lookup-modal", this.$el).modal('hide');
        					this.retain_state = true;
        					this.getKVLookups();
        				}
        				
        			}.bind(this),
        		  
        			// Handle errors
        			error: function(jqXHR, textStatus, errorThrown){
        				if( jqXHR.status != 403 ){
        					console.info('KV store collection disablement failed');
        				}
        			}.bind(this)
        	});
        	
        },
        
        /**
         * Open a dialog to disable the KV store lookup.
         */
        openDisableKVLookupDialog: function(ev){
        	
        	// Get the lookup that is being requested to remove
        	var lookup = $(ev.target).data("name");
        	var namespace = $(ev.target).data("namespace");
        	var owner = $(ev.target).data("owner");
        	
        	// Record the info about the lookup to remove
        	$("#disable-this-lookup", this.$el).data("name", lookup);
        	$("#disable-this-lookup", this.$el).data("namespace", namespace);
        	$("#disable-this-lookup", this.$el).data("owner", owner);
        	
        	// Show the info about the lookup to remove
        	$(".disable-lookup-name", this.$el).text(lookup);
        	$(".disable-lookup-namespace", this.$el).text(namespace);
        	$(".disable-lookup-owner", this.$el).text(owner);
        	
        	// Show the modal
			$.when(this.disableModal.show())
			.done(function(){
				this.disableLookup(lookup, namespace, owner);
			}.bind(this));
		return false;
        	
        },
        
        /**
         * Apply a filter to the table
         */
        goFilter: function(ev){
        	
        	var code = ev.keyCode || ev.which;
        	
            if (code == 13){
            	ev.preventDefault();
            }
        	
        	this.applyFilter();
        },
        
        /**
         * Apply a filter to the table
         */
        applyFilter: function(){
        	
        	// Determine if we even need to apply this filter
        	var applied_filter_signature = "" + this.filter_type + ":" + this.filter_app + ":" + this.filter_scope + ":" + $('#free-text-filter').val();
        	
        	if(applied_filter_signature === this.applied_filter){
        		return;
        	}
        	
        	// Persist the signature for this filter
        	this.applied_filter = applied_filter_signature;
        	
        	// Get the type filter
        	if( this.filter_type !== null ){
        		this.data_table.columns(1).search( "^" + this.escapeRegEx(this.filter_type) + "$", true );
        	}
        	else{
        		this.data_table.columns(1).search( "" );
        	}
        	
        	// Get the app filter
        	if( this.filter_app !== null ){
        		this.data_table.columns(2).search( "^" + this.escapeRegEx(this.filter_app) + "$", true );
        	}
        	else{
        		this.data_table.columns(2).search( "" );
        	}
        	
        	// Get the scope filter
        	if( this.filter_scope !== null ){
        		this.data_table.columns(3).search( "^" + this.escapeRegEx(this.filter_scope) + "$", true );
        	}
        	else{
        		this.data_table.columns(3).search( "" );
        	}
        	
        	// Apply the text filter
        	this.filter_text = $('#free-text-filter').val();
        	this.data_table.columns(0).search( $('#free-text-filter').val() ).draw();
        },
		
		/**
         * Open the lookup in search or make the lookup transform.
         */
		openInSearch: function(e){
			e.preventDefault();

			if(this.lookup_transform_editor === null){
				this.lookup_transform_editor = new LookupTransformCreateView({
					el : $('#lookup-transform-edit', this.$el),
					callback : function(){
						this.retain_state = true;
						this.lookup_transforms.fetch({
							success: function() {
							  console.info("Successfully retrieved the list of lookup transforms");
							}.bind(this),
							error: function() {
							  console.error("Unable to fetch the lookup transforms");
							}.bind(this)
						});
					}.bind(this),
					kv_collections : this.kv_lookups
				});
	
				this.lookup_transform_editor.render();
			}

			// Get the transform information for KV lookups
			var data = $(e.currentTarget).data();
			
			if(data.owner && data.namespace && data.name){
				this.lookup_transform_editor.openInSearchOrCreateTransform(data.owner, data.namespace, data.name);
			}
		},

        /**
         * Get the description for the app name
         */
        getAppDescriptionFromName: function(name){
        	
    		for(var c = 0; c < this.apps.models.length; c++){
    			if(this.apps.models[c].entry.attributes.name === name){
    				return this.apps.models[c].entry.associated.content.attributes.label;
    			}
    		}
    		
    		return name;
		},
		
		/**
		 * Confirm and then delete the given CSV lookup.
		 */
		confirmAndDeleteLookup: function(ev){
        	// Get the lookup that is being requested to remove
        	var lookup = $(ev.target).data("name");
        	var namespace = $(ev.target).data("namespace");
			var owner = $(ev.target).data("owner");
			var type = $(ev.target).data("type");
        	
        	// Record the info about the lookup to remove
        	$("#delete-this-lookup", this.$el).data("name", lookup);
        	$("#delete-this-lookup", this.$el).data("namespace", namespace);
			$("#delete-this-lookup", this.$el).data("owner", owner);
			$("#delete-this-lookup", this.$el).data("type", type);
        	
        	// Show the info about the lookup to remove
        	$(".delete-lookup-name", this.$el).text(lookup);
        	$(".delete-lookup-namespace", this.$el).text(namespace);
        	$(".delete-lookup-owner", this.$el).text(owner);
        	
        	// Show the modal
			$.when(this.deleteModal.show())
				.done(function(){
					if(type === 'csv'){
						this.deleteCSVLookup(lookup, namespace, owner);
					}
					else{
						this.deleteKVLookup(lookup, namespace);
					}
				}.bind(this));
        	return false;
		},

		/**
		 * Delete the given CSV lookup.
		 */
		deleteCSVLookup: function(lookup_name, namespace, owner){
			var lookup = new SplunkDBaseModel();

			lookup.fetch({
				url: Splunk.util.make_url('/splunkd/__raw/servicesNS', encodeURIComponent(owner), encodeURIComponent(namespace), '/data/lookup-table-files/', encodeURIComponent(lookup_name)),
				success: function() {
					lookup.destroy({
						success: function() {
							this.retain_state = true;
							this.getCSVLookups();
						}.bind(this),
						error: function(model, response) {
							alert("Lookup file could not be deleted: " + response.responseJSON.messages[0].text);
						}.bind(this)
					});
				}.bind(this),
				error: function() {
					alert("Lookup file could not be deleted");
				}.bind(this)
			});
		},

		/**
		 * Delete the given KV lookup.
		 */
		deleteKVLookup: function(lookup_name, namespace){			
			var lookup = new SplunkDBaseModel();

			lookup.fetch({
				url: Splunk.util.make_url('/splunkd/__raw/servicesNS/nobody/' + encodeURIComponent(namespace) + '/storage/collections/config/' + encodeURIComponent(lookup_name)),
				success: function() {
					lookup.destroy({
						success: function() {
							this.retain_state = true;
							this.getKVLookups();
						}.bind(this),
						error: function(model, response) {
							alert("Lookup file could not be deleted: " + response.responseJSON.messages[0].text);
						}.bind(this)
					});
				}.bind(this),
				error: function() {
					alert("Lookup file could not be deleted");
				}.bind(this)
			});
		},
        
        /**
         * Got the CSV lookups
         */
        gotCSVLookups: function(){
        	this.renderLookupsList();
        },
        
        /**
         * Got the KV store lookups
         */
        gotKVLookups: function(){
        	this.renderLookupsList();
        },
        
        /**
         * Got the apps
         */
        gotApps: function(){
        	this.renderLookupsList();
        },
        
        /**
         * Got the lookup transforms
         */
        gotLookupTransforms: function(){
        	this.renderLookupsList();
        },
        
        /**
         * Determine if the string end with a sub-string.
         */
        endsWith: function(str, suffix) {
            return str.indexOf(suffix, str.length - suffix.length) !== -1;
        },
        
        /**
         * Determine if the lookup a supported one
         */
        isSupportedLookup: function(lookup){
        	
        	if(this.endsWith(lookup.name, ".default")){
        		return false;
        	}
        	
        	else if(lookup.name === ".DS_Store"){
        		return false;
        	}
        	
        	else{
        		return true;
        	}
        	
        },
        
        /**
         * Get a count of the lookups that exist.
         */
        getLookupsCount: function(){
        	var lookups = this.getLookupsJSON();
        	
        	if(lookups){
        		return lookups.length;
        	}
        	else{
        		return 0;
        	}
        },
        
        /**
         * Get the lookups list in JSON format
         */
        getLookupsJSON: function(){
        	
        	var lookups_json = [];
        	var new_entry = null;
        	var endpoint_owner = null;
        	
        	// Add the CSV lookups
        	for(var c = 0; c < this.csv_lookups.models.length; c++){
        		
        		// Determine what owner to use for loading the user's lookup
        		if(this.csv_lookups.models[c].entry.acl.attributes.sharing === 'global' || this.csv_lookups.models[c].entry.acl.attributes.sharing === 'app'){
        			endpoint_owner = 'nobody';
        		}
        		else{
        			endpoint_owner = this.csv_lookups.models[c].entry.acl.attributes.owner;
        		}
        		
        		// Make the entry
        		new_entry = {
        				'name': this.csv_lookups.models[c].entry.attributes.name,
        				'author': this.csv_lookups.models[c].entry.attributes.author,
        				'updated': this.csv_lookups.models[c].entry.attributes.updated,
        				'namespace': this.csv_lookups.models[c].entry.acl.attributes.app,
        				'owner': this.csv_lookups.models[c].entry.acl.attributes.owner,
        				'type' : 'csv',
        				'sharing' : this.csv_lookups.models[c].entry.acl.attributes.sharing,
						'endpoint_owner' : endpoint_owner,
						'can_write' : this.csv_lookups.models[c].entry.acl.attributes.can_write
        		};
        		
        		// Don't include KMZ files
        		if(!this.endsWith(this.csv_lookups.models[c].entry.attributes.name, ".kmz")){
        			lookups_json.push(new_entry);
        		}
        	}
        	
        	// Add the KV store lookups
        	for(var c = 0; c < this.kv_lookups.models.length; c++){
        		new_entry = {
        				'name': this.kv_lookups.models[c].entry.attributes.name,
        				'author': this.kv_lookups.models[c].entry.attributes.author,
        				'updated': this.kv_lookups.models[c].entry.attributes.updated,
        				'namespace': this.kv_lookups.models[c].entry.acl.attributes.app,
						'owner': this.kv_lookups.models[c].entry.acl.attributes.owner,
        				'type' : 'kv',
        				'endpoint_owner' : 'nobody',
						'disabled': this.kv_lookups.models[c].entry.associated.content.attributes.disabled,
						'can_write' : this.kv_lookups.models[c].entry.acl.attributes.can_write
        		};
        		
        		lookups_json.push(new_entry);
        	}
        	
        	return lookups_json.filter(this.isSupportedLookup.bind(this));
        },
        
        /**
         * Get the apps list in JSON format
         */
        getAppsJSON: function(only_include_those_with_lookups){
        	
        	// Set a default for the parameter
        	if (typeof only_include_those_with_lookups === "undefined") {
        		only_include_those_with_lookups = true;
        	}
        	
        	// If we don't have the apps yet, then just return an empty list for now
        	if(!this.apps){
        		return [];
        	}
        	
        	var apps_json = [];
        	var new_entry = null;
        	
        	for(var c = 0; c < this.apps.models.length; c++){
        		
        		new_entry = {
        				'name': this.apps.models[c].entry.attributes.name,
        				'label': this.apps.models[c].entry.associated.content.attributes.label
        		};
        		
        		// Filter out the items that are not for an app that exposes a lookup
        		if(only_include_those_with_lookups){
        			
	        		// Find out of the item is for an app that publishes a CSV lookup
	        		for(var d = 0; d < this.csv_lookups.models.length; d++){
	        			
	        			if(this.csv_lookups.models[d].entry.acl.attributes.app === this.apps.models[c].entry.attributes.name){
	        				apps_json.push(new_entry);
	        				break;
	        			}
	        		}
	        		
	        		// Find out of the item is for an app that publishes a KV lookup
	        		for(var d = 0; d < this.kv_lookups.models.length; d++){
	        			
	        			if(this.kv_lookups.models[d].entry.acl.attributes.app === this.apps.models[c].entry.attributes.name){
	        				apps_json.push(new_entry);
	        				break;
	        			}
	        			
	        		}
        		}
        		
        		// Otherwise, just include all of them
        		else{
        			apps_json.push(new_entry);
        		}
        		
        	}
        	
        	// Deduplicate the list
        	apps_json = _.uniq(apps_json, function(item, key, a) { 
        	    return item.name;
        	});
        	
        	return apps_json;
        },
        
        /**
         * Get the lookup transforms in JSON format.
         */
        getLookupTransformsJSON: function(){
        	
        	// If we don't have the lookup transforms yet, then just return an empty list for now
        	if(!this.lookup_transforms){
        		return [];
        	}
        	
        	var transforms = [];
        	
        	for(var c = 0; c < this.lookup_transforms.models.length; c++){
        		
        		// Add entries for the KV store
        		if(this.lookup_transforms.models[c].entry.associated.content.attributes.type == "kvstore"){
        			transforms.push({
            			'transform': this.lookup_transforms.models[c].entry.attributes.name,
            			'collection': this.lookup_transforms.models[c].entry.associated.content.attributes.collection
            		});
        		}
        		
        		// Add entries for the CSV files
        		else if(this.lookup_transforms.models[c].entry.associated.content.attributes.type == "file"){
        			transforms.push({
            			'transform': this.lookup_transforms.models[c].entry.attributes.name,
            			'filename': this.lookup_transforms.models[c].entry.associated.content.attributes.filename
            		})
        		}
        	}
        	
        	return transforms;
        },
        
        /**
         * Get the transform name of the given lookup.
         */
        getLookupTransform: function(lookup_name){
        	
        	var transforms = this.getLookupTransformsJSON();
        	
        	for(var c = 0; c < transforms.length; c++){
        		
        		// Lookup KV store lookups
        		if(transforms[c].collection === lookup_name){
        			return transforms[c].transform;
        		}
        		
        		// Lookup CSV store lookups
        		if(transforms[c].filename === lookup_name){
        			return transforms[c].transform;
        		}
        		
        	}
        },
        
        /**
         * Render the list of lookups.
         */
        renderLookupsList: function(retainState){
        	
        	// Load a default for the retainState parameter
        	if( typeof retainState == 'undefined' ){
        		retainState = this.retain_state;
        	}
        	
        	// Get the template
            var lookup_list_template = $('#lookup-list-template', this.$el).text();
            
        	$('#content', this.$el).html(_.template(lookup_list_template, {
        		'lookups' : this.getLookupsJSON(),
        		'apps' : this.getAppsJSON(),
        		'transforms' : this.getLookupTransformsJSON(),
        		'kv_lookups_supported' : this.kv_lookups_supported,
        		'getAppDescriptionFromName' : this.getAppDescriptionFromName.bind(this),
        		'getLookupTransform' : this.getLookupTransform.bind(this),
        		'filter_app': this.filter_app,
        		'filter_type' : this.filter_type,
        		'filter_scope': this.filter_scope,
        		'filter_text': this.filter_text,
        		'lookups_count' : this.getLookupsCount()
        	}));
        	
            // Make the table filterable, sortable and paginated with data-tables
            this.data_table = $('#table', this.$el).DataTable( {
                "iDisplayLength": 25,
                "bLengthChange": false,
                "searching": true,
                "aLengthMenu": [[ 25, 50, 100, -1], [25, 50, 100, "All"]],
                "bStateSave": true,
                "fnStateLoadParams": function (oSettings, oData) {
                	return retainState;
                },
                "aaSorting": [[ 1, "asc" ]],
                "aoColumns": [
                              null,                   // Name
                              null,                   // Type
                              null,                   // App
                              null,                   // Owner
                              { "bSortable": false }  // Actions
                            ]
            } );
            
            // Update the filter text
            this.setTypeFilter(this.filter_type);
            
            // Update the app filter
            this.setAppFilter(this.filter_app);
            
            // Update the scope filter
            this.setScopeFilter(this.filter_scope);
        },
        
        /**
         * Render the page.
         */
        render: function () {
			this.$el.html(Template);
			
			// Render the delete modal
			this.deleteModal = new ModalDialog({
				el: $('#delete-lookup-modal', this.$el),
				title: 'Delete Lookup',
				body: 'Are you sure you want to delete this lookup?' +
					'<table class="delete-lookup-info-table">' +
					'   <tr>' +
					'	    <td class="delete-lookup-info">Lookup</td>' +
					'	    <td class="delete-lookup-name"></td>' +
					'    </tr>' +
					'    <tr>' +
					'	    <td class="delete-lookup-info">Namespace</td>' +
					'	    <td class="delete-lookup-namespace"></td>' +
					'    </tr>' +
					'    <tr>' +
					'	    <td class="delete-lookup-info">Owner</td>' +
					'	    <td class="delete-lookup-owner"></td>' +
					'    </tr>' +
					'</table>',
				ok_button_title: 'Yes, Delete'
			});

			this.deleteModal.render();

			// Render the disable modal
			this.disableModal = new ModalDialog({
				el: $('#disable-lookup-modal', this.$el),
				title: 'Disable Lookup',
				body: 'Are you sure you want to disable this lookup?' +
					'<table class="disable-lookup-info-table">' +
					'   <tr>' +
					'	    <td class="disable-lookup-info">Lookup</td>' +
					'	    <td class="disable-lookup-name"></td>' +
					'    </tr>' +
					'    <tr>' +
					'	    <td class="disable-lookup-info">Namespace</td>' +
					'	    <td class="disable-lookup-namespace"></td>' +
					'    </tr>' +
					'    <tr>' +
					'	    <td class="disable-lookup-info">Owner</td>' +
					'	    <td class="disable-lookup-owner"></td>' +
					'    </tr>' +
					'</table>',
				ok_button_title: 'Yes, Disable'
			});

			this.disableModal.render();
        }
    });
    
    return LookupListView;
});