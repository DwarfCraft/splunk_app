require([
    "underscore",
    "backbone",
    "collections/SplunkDsBase",
    "splunkjs/mvc",
    "jquery",
], function(
    _,
    Backbone,
    SplunkDsBaseCollection,
    mvc,
    $
){
	
	var KVLookups = SplunkDsBaseCollection.extend({
	    url: '/splunkd/__raw/servicesNS/nobody/lookup_editor/storage/collections/config?count=-1',
	    initialize: function() {
	      SplunkDsBaseCollection.prototype.initialize.apply(this, arguments);
	    }
	});
	
	kv_lookups = new KVLookups();
	
	kv_lookups.fetch({
        complete: function(jqXHR, textStatus){
        	if( jqXHR.status == 404){
        		$(".show-kv-supported-only").hide();
            	$(".show-kv-unsupported-only").show();
        	}
        }.bind(this)
    });
	
});