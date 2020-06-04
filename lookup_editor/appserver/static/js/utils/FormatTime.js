require.config({
    paths: {
		moment: '../app/lookup_editor/js/lib/moment/moment'
    }
});

define([
	"moment",
], function(
	moment
){
    /**
     * Format the time into the standard format.
     * 
     * @param value The value of the time (a number) to convert into a string
     * @param includes_microseconds Whether the value is considered as including microseconds (epoch x 1000) 
     */
    return function(value, includes_microseconds){

        if(typeof includes_microseconds === "undefined"){
            includes_microseconds = false;
        }

        if(/^\d+([.]\d+)?$/.test(value)){
            var epoch = parseFloat(value, 10);
            
            if(!includes_microseconds){
                // Moment expects micro-seconds in the epoch time value, so adjust accordingly
                epoch = epoch * 1000;
            }

            return moment(epoch).format('YYYY/MM/DD HH:mm:ss');
        }
        else{
            return value;
        }
    };
});