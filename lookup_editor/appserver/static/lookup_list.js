
require.config({
    paths: {
        lookup_list: "../app/lookup_editor/js/views/LookupListView"
    }
});

require([
         "jquery",
         "underscore",
         "backbone",
         "lookup_list",
         "splunkjs/mvc/simplexml/ready!"
     ], function(
         $,
         _,
         Backbone,
         LookupListView
     )
     {
         
         var lookupListView = new LookupListView({
        	 el: $('#lookups_list')
         });
         
         lookupListView.render();
     }
);