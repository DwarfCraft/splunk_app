
require.config({
    paths: {
        text: "../app/lookup_editor/js/lib/text",
        console: '../app/lookup_editor/js/lib/console'
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
    "splunkjs/mvc/simpleform/input/text",
    "collections/services/data/TransformsLookups",
    "models/services/data/TransformsLookup",
    "text!../app/lookup_editor/js/templates/LookupTransformCreateView.html",
    "util/splunkd_utils",
    "css!../app/lookup_editor/css/LookupTransformCreateView.css",
], function(
    _,
    Backbone,
    SplunkDBaseModel,
    SplunkDsBaseCollection,
    mvc,
    $,
    SimpleSplunkView,
    TextInput,
    TransformsLookups,
    TransformsLookup,
    Template,
    splunkd_utils
){

	var KVLookups = SplunkDsBaseCollection.extend({
	    url: '/splunkd/__raw/servicesNS/nobody/-/storage/collections/config?count=-1',
	    initialize: function() {
	      SplunkDsBaseCollection.prototype.initialize.apply(this, arguments);
	    }
	});

    var LookupTransformCreateView = SimpleSplunkView.extend({
        className: "LookupTransformCreateView",
        
        defaults: {
            callback: null,
            kv_collections: null
        },
        
        /**
         * Initialize the class.
         */
        initialize: function() {
            this.options = _.extend({}, this.defaults, this.options);
            
            this.callback = this.options.callback;

            // This will contain the list of the transforms and kv collections
            this.transforms = null;
            this.kv_collections = this.options.kv_collections;

            // This will be the lookup transform that was created
            this.lookup_transform = null;

            // This will be the control for the transform name
            this.name_input = null;
        },

        events: {
            "click #save-transform" : "onCreate",

            // This is used to fix some wierdness with bootstrap and input focus
            "shown #lookup-transform-modal" : "focusView",
        },

        /**
         * Make a link to open the lookup in search.
         */
        makeSearchLink: function(lookup_name){
            return "search?q=" + encodeURIComponent("| inputlookup append=t " + lookup_name);
        },

        /**
         * Show the modal.
         */
        show: function(owner, namespace, lookup) {
    
            // Clear the existing value so that it doesn't carry over
            if(mvc.Components.getInstance("transform-name")){
                mvc.Components.getInstance("transform-name").val('');
            }
                
            // Hide the warning message
            this.hideWarningMessage();

            this.$('.main-content').show();
            this.$('.no-fields-content').hide();
            this.$('#save').show();

            // Make sure that the lookup has fields defined
            $.when(this.getFieldsForLookup(lookup)).done(function(fields){

                if(fields.length > 0){
                    this.owner = owner;
                    this.namespace = namespace;
                    this.lookup = lookup;
        
                    this.save_pressed = false;
                }
                else {
                    this.$('.main-content').hide();
                    this.$('.no-fields-content').show();
                    this.$('#save').hide();
                }

                // Open the modal
                this.$('#lookup-transform-modal').modal();
            }.bind(this));

        },

        /**
         * Fixes an issue where clicking an input loses focus instantly due to a problem in Bootstrap.
         * 
         * http://stackoverflow.com/questions/11634809/twitter-bootstrap-focus-on-textarea-inside-a-modal-on-click
         */
        focusView: function(){
            this.$('#transform-name input').focus();
        },

        /**
         * Create the transform and call the callback once it is done if necessary.
         */
        onCreate: function(){
            this.save_pressed = true;

            if(this.validateForm()){
                $.when(this.createTransform(this.owner, this.namespace, this.lookup, mvc.Components.getInstance("transform-name").val())).done(function(){
                    if(this.callback){
                        this.callback();
                    }
                }.bind(this));
            }
        },
    
        /**
         * Show a warning message on the form.
         */
        showWarningMessage: function(message){
            this.$('.alert').show();
            this.$('#message').text(message);
        },

        /**
         * Hide the warning message.
         */
        hideWarningMessage: function(){
            this.$('.alert').hide();
        },

        /**
         * Create the transform.
         */
        createTransform: function(owner, namespace, lookup, transform_name) {
            // Create the model to save
            var lookupTransform = new TransformsLookup();

            // Get a promise ready
            var promise = jQuery.Deferred();

            // Get the list of fields for this lookup
            $.when(this.getFieldsForLookup(lookup)).done(function(fields){

                var fields_escaped = _.map(fields, function(field){ return field.indexOf(" ") >= 0 ? '"' + field + '"' : field; });

                // Modify the model
                lookupTransform.entry.content.set('collection', lookup);
                lookupTransform.entry.content.set('external_type', 'kvstore');
                lookupTransform.entry.content.set('name', transform_name);
                lookupTransform.entry.content.set('fields_list', fields_escaped.join(","));

                // Kick off the request to edit the entry
                lookupTransform.save({}, {
                    data: {
                        app: namespace,
                        owner: 'nobody',
                    },
                }).done(function() {
                    // If successful, close the dialog and run the search
                    this.$('#lookup-transform-modal').modal('hide');
                    this.openInSearch(transform_name);

                    // Clear the transforms list so that we refresh the list
                    this.transforms = null;

                    promise.resolve();
                }.bind(this)).fail(function(response) {
                    if(response.status === 409){
                        this.showWarningMessage('A transform with this name already exists');
                    }
                    else if(response.status === 403){
                        this.showWarningMessage('You do not have permission to create a lookup transform');
                    }
                    else{
                        this.showWarningMessage('The transform could not be created (got an error from the server)');
                    }
                    
                    // Otherwise, show a failure message
                    promise.reject();
                }.bind(this));
            }.bind(this));
            
            // Return the promise
            return promise;
        },

        /**
         * Validate the form.
         */
        validateForm: function() {

            if(mvc.Components.getInstance("transform-name") === undefined || mvc.Components.getInstance("transform-name").val() === undefined){
                return false;
            }

            if(mvc.Components.getInstance("transform-name").val().length === 0){
                if(this.save_pressed){
                    this.showWarningMessage('Please enter the name of the transform to create');
                }
                return false;
            }
            else{
                return true;
            }
        },

        /**
         * Get the fields list for the given lookup name.
         */
        getFieldsForLookup: function(lookup_name){
            // Get a promise ready
            var promise = jQuery.Deferred();

            $.when(this.getKVCollections()).done(function(){
                var fields = null;

                // Find the collection
                for(var c = 0; c < this.kv_collections.models.length; c++){

                    var entry = this.kv_collections.models[c].entry;

                    if(entry.attributes.name === lookup_name){
                        // Filter down the attributes down to the fields
                        fields = _.keys(entry.content.attributes).filter(function(attribute){
                            return attribute.indexOf('field.') === 0;
                        });

                        // Strip out the prefix of "field."
                        fields = fields.map(function(attribute){
                            return attribute.substr(6, 100);
                        });

                        // Add the _key field to the list if we got some fields
                        if(fields.length > 0){
                            fields.push('_key');
                        }
                    }
                }

                // Resolve the promise
                promise.resolve(fields);

            }.bind(this));
    
            // Return the promise
            return promise;
        },

        /**
         * Get the transform name for the given KV store collection (if it exists).
         */
        getTransformForCollection: function(collection_name){

            // Get a promise ready
            var promise = jQuery.Deferred();

            $.when(this.getTransforms()).done(function(){
                // Determine if a transform already exists
                var existing_transform = null;

                for(var c = 0; c < this.transforms.models.length; c++){
                    if(collection_name == this.transforms.models[c].entry.associated.content.attributes.collection){
                        existing_transform = this.transforms.models[c].entry.attributes.name;
                    }                    
                }

                promise.resolve(existing_transform);
            }.bind(this));

            return promise;    
        },

        /**
         * Open the lookup in search or open the form to create the transform
         */
        openInSearchOrCreateTransform: function(owner, namespace, lookup){

            // Get the transforms
            $.when(this.getTransformForCollection(lookup)).done(function(lookup_transform){

                // If so, open it
                if(lookup_transform){
                    this.openInSearch(lookup_transform);

                } else {
                    // Otherwise, offer to create it
                    this.show(owner, namespace, lookup);
                }
            }.bind(this));
        },

        /**
         * Open the given lookup in the search page.
         */
        openInSearch: function(lookup_transform) {
            window.open('search?q=%7C%20inputlookup%20append%3Dt%20' + lookup_transform, '_blank');
        },

        /**
         * Get the list of transforms.
         */
        getTransforms: function(){
            // Get a promise ready
            var promise = jQuery.Deferred();

            // Return the existing results if we have them
            if(this.transforms !== null && this.transforms.models && this.transforms.models.length > 0){
                promise.resolve(this.transforms);
                return;
            }

            // Fetch the promises otherwise
            this.transforms = new TransformsLookups();

            this.transforms.fetch({
                success: function () {
                    promise.resolve(this.transforms);
                    console.info("Successfully retrieved the list of transforms");
                }.bind(this),
                error: function () {
                    promise.reject();
                    console.error("Unable to fetch the transforms");
                }.bind(this)
            });

            return promise;
        },

        /**
         * Get the list of KV store collections.
         */
        getKVCollections: function(){
            // Get a promise ready
            var promise = jQuery.Deferred();

            // Return the existing results if we have them
            if(this.kv_collections !== null){
                promise.resolve(this.kv_collections);
                return;
            }

            this.kv_collections = new KVLookups();

            this.kv_collections.fetch({
                success: function () {
                    promise.resolve(this.kv_collections);
                    console.info("Successfully retrieved the list of KV store collections");
                }.bind(this),
                error: function () {
                    promise.reject();
                    console.error("Unable to fetch the collections");
                }.bind(this)
            });

            return promise;
        },

        /**
         * Render the page.
         */
        render: function() {
            // Get a promise ready
            var promise = jQuery.Deferred();

            this.$el.html(Template);
            
            // Get the transforms and KV store collections
            $.when(this.getTransforms(), this.getKVCollections()).done(function(){

                // Make the input for the transform name
                this.name_input = new TextInput({
                    "id": "transform-name",
                    "searchWhenChanged": false,
                    "el": $('#transform-name', this.$el)
                }, {tokens: true}).render();
                            
                this.name_input.on("change", function(newValue) {
                    this.validateForm();
                }.bind(this));

                promise.resolve();
            }.bind(this));

            return promise;
        }
    });
   
    return LookupTransformCreateView;
});