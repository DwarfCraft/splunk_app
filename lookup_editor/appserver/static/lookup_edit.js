
require.config({
    paths: {
    	lookup_edit: "../app/lookup_editor/js/views/LookupEditView"
    }
});

require([
         "jquery",
         "underscore",
         "backbone",
         "lookup_edit",
         "splunkjs/mvc/simplexml/ready!"
     ], function(
         $,
         _,
         Backbone,
         LookupEditView
     )
     {
         
         var lookupEditView = new LookupEditView({
        	 el: $('#lookups_editor')
         });
         
         lookupEditView.render();
     }
);