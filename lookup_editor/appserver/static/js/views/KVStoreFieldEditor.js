require.config({
    paths: {
        text: "../app/lookup_editor/js/lib/text",
        console: '../app/lookup_editor/js/lib/console',
        kv_store_field_view: '../app/lookup_editor/js/views/KVStoreFieldView'
    }
});

define([
    "underscore",
    "backbone",
    "splunkjs/mvc",
    "util/splunkd_utils",
    "jquery",
    "splunkjs/mvc/simplesplunkview",
    "kv_store_field_view",
    "text!../app/lookup_editor/js/templates/KVStoreFieldEditor.html",
    "css!../app/lookup_editor/css/KVStoreFieldEditor.css"
], function(
    _,
    Backbone,
    mvc,
    splunkd_utils,
    $,
    SimpleSplunkView,
    KVStoreFieldView,
    Template
){

    var KVStoreFieldEditor = SimpleSplunkView.extend({
        className: "KVStoreFieldEditor",
        
        defaults: {
        	'default_field_count' : 5 // This dictates the number of default fields to show when creating a new lookup
        },
        
        events: {
        	"click .add-additional-field" : "doAddField"
        },
        
        initialize: function() {
        	this.options = _.extend({}, this.defaults, this.options);
        	
        	this.field_views = [];
        	this.field_counter = 0;
        	
        	this.default_field_count = this.options.default_field_count;
        	
        	this.listenTo(Backbone, "kv_field:remove", this.removeField.bind(this));
        },
        
        /**
         * Make sure that the fields are valid. If this function returns a string, then the input is invalid. Otherwise, "true" will be returned.
         */
        validate: function(){
        	
        	/*
        	 * Check to make sure at least one field is defined.
        	 */
        	var has_field_defined = false;
        	
        	// Make sure that a field is defined (and clear any validation errors while your at it)
        	for(var c = 0; c < this.field_views.length; c++){
        		if(this.field_views[c].hasFieldName()){
        			has_field_defined = true;
        		}
        		
        		// Let's hide the error message, we will post another one if we need to
        		this.field_views[c].hideErrorMessage();
        	}
        	
        	if(!has_field_defined){
        		return "At least one field needs to be defined";
        	}
        	
        	/* Make sure that the user doesn't attempt to use a field that is the parent of one of the other fields.
        	 * 
        	 * For example, the following fields could not be a valid collection:
        	 *    
        	 *    field.car = string
        	 *    field.car.model = string
        	 *    field.car.make = string
        	 *    
        	 * That cannot be used because there is no way to have a value for "car" since its value is it's children. The JSON will look like this:
        	 * 
        	 *    "car":{
        	 * 			"model": "Focus ST",
        	 * 			"make": "Ford"
        	 * 	  }
        	 * 
        	 * We need to make sure that none of the lineages are field names.
        	 */
        	// 
        	
        	// Make a list of lineages. If any field tries to use one of these, then it is invalid.
        	var lineages = [];
        	var lineage = null;
        	var lineage_partial = null;
        	
        	for(c = 0; c < this.field_views.length; c++){
        		if(this.field_views[c].hasFieldName()){
        			
        			// Rebuild the lineage but without the final entry (e.g. make "car.model.sub_model" just "car.model"
        			lineage = this.field_views[c].getFieldName().split(".").slice(0, -1);
        			
        			lineage_partial = null;
        			
        			for(var d = 0; d < lineage.length; d++){
        				
        				if(lineage_partial === null){
        					lineage_partial = lineage[d];
        				}
        				else{
        					lineage_partial = lineage_partial + "." + lineage[d];
        				}
        				
        				// Add the lineage to the list
        				lineages.push(lineage_partial);
        			}
        		}
        	}
        	
        	// Now check the fields and make sure none match any of the lineages
        	for(c = 0; c < this.field_views.length; c++){
        		
        		for(var d = 0; d < lineages.length; d++){
        			if(lineages[d] === this.field_views[c].getFieldName()){
        				this.field_views[c].showErrorMessage("This field's name cannot co-exist with another field that has '" + lineages[d] + '" in its name');
        				return 'The field "' + this.field_views[c].getFieldName() + '" cannot be used';
        			}
        		}
        	}
        	
        	
        	/*
        	 * Make sure we don't have multiple of the same field
        	 */
        	var duplicate_name_error = false;
        	
        	for(c = 0; c < this.field_views.length; c++){
        		
        		for(var d = 0; d < this.field_views.length; d++){
        			
        			// Don't compare the item to itself, don't compare if one is blank, otherwise, compare away!
        			if(c !== d && this.field_views[c].hasFieldName()){
        				if( this.field_views[c].getFieldName() === this.field_views[d].getFieldName()){
        					this.field_views[c].showErrorMessage("Another field has this name already");
        					this.field_views[d].showErrorMessage("Another field has this name already");
        					duplicate_name_error = true;
        				}
        			}
        		}
        	}
        	
        	if(duplicate_name_error){
        		return "Fields cannot have the same name";
        	}
        	
        	// Make sure the field doesn't have $ or nulls
        	var invalid_field_name = false;
        	
        	for(c = 0; c < this.field_views.length; c++){
        		if(this.field_views[c].getFieldName().indexOf("$") > -1){
        			this.field_views[c].showErrorMessage("The name cannot contain a $");
        			invalid_field_name = true;
        		}
        	}
        	
        	if(invalid_field_name){
        		return "Field names cannot contain $ characters";
        	}
        	
        	// No issues found, yay!
        	return true;
        },
        
        /**
         * Add a new field view instance.
         */
        removeField: function(unique_identifier){
        	this.field_views = _.without(this.field_views, _.findWhere(this.field_views, {unique_identifier: unique_identifier}));
        },
        
        /**
         * Add a new field view instance.
         */
        doAddField: function(){
        	this.addFieldView('', 'string');
        },
        
        /**
         * Add an other field view widget.
         */
        addFieldView: function(field_name, field_type){
        	
        	// Make the placeholder for the view
        	var kv_store_field_view_selector = 'kv_store_field_' + this.field_counter;
        	
        	$('<div id="' + kv_store_field_view_selector + '"></div>').appendTo("#kv-store-fields");
        		
        	// Make the view instance
        	var kv_store_field_view = new KVStoreFieldView({
        		'el' : $('#' + kv_store_field_view_selector, this.$el),
        		'unique_identifier' : kv_store_field_view_selector
        	});
        	
        	// Add the view to the list
        	this.field_views.push(kv_store_field_view);
        	
        	// Render the added view
        	kv_store_field_view.render();
        	
        	// Increment the counter so that the next view has a different ID
        	this.field_counter++;
        	
        },
        
        /**
         * Modify the KV store collection schema
         */
        modifyKVStoreLookupSchema: function(namespace, lookup_file, owner, replicate, success_callback){
        	
        	// Set a default value for the owner and callback
        	if( typeof owner == 'undefined' ){
        		owner = 'nobody';
        	}
        	
        	if( typeof success_callback == 'undefined' ){
        		success_callback = null;
        	}
        	
        	// Make the data that will be posted to the server
        	var data = {};
        	
        	for(var c = 0; c < this.field_views.length; c++){
        		if(this.field_views[c].hasFieldName()){
        			data['field.' + this.field_views[c].getFieldName()] = this.field_views[c].getFieldType();
        		}
        	}
        	
        	// Enable replication if necessary
        	data.replicate = replicate;
        	
			// Perform the call
        	$.ajax({
        			url: splunkd_utils.fullpath(['/servicesNS', owner, namespace, 'storage/collections/config', lookup_file].join('/')),
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
        				
        				// Run the success callback if one is defined
        				if(success_callback){
        					success_callback();
        				}
        				
        			  
        			}.bind(this),
        		  
        			// Handle cases where the file could not be found or the user did not have permissions
        			complete: function(jqXHR, textStatus){
        				if( jqXHR.status == 403){
        					console.info('Inadequate permissions');
        					this.showWarningMessage("You do not have permission to make a KV store collection", true);
        				}
        			  
        			}.bind(this),
        		  
        			// Handle errors
        			error: function(jqXHR, textStatus, errorThrown){
        				if( jqXHR.status != 403 ){
        					console.info('KV store collection creation failed');
        					this.showWarningMessage("The KV store collection could not be created", true);
        				}
        			}.bind(this)
        	});
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

        render: function () {

        	// Render the base HTML
        	this.$el.html(_.template(Template, {
        		
        	}));
        	
        	var fields = {};
        	
        	// Add an entry for each of the fields
        	for(var field in fields){
        		this.addFieldView(field, fields[field]);
        	}
        	
        	// Add some default fields if necessary
        	if(this.field_views.length === 0){
        		for(var c = 0; c < this.default_field_count; c++){
        			this.addFieldView('', 'string');
        		}
			}

        }
    });
    
    return KVStoreFieldEditor;
});