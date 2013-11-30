(function($){
    $.fn.extend({ 
        leanModal: function(options) {
            var defaults = {
                top: 50,
                overlay: 0.5,
                closeButton: null
            }
            var overlay = $('<div id="lean_overlay"></div>');
            $('body').append(overlay);
            options =  $.extend(defaults, options);
            var o = options;
            var modal_id = $('<div>')
                .clone()
                .append($(this).show());
            $('#lean_overlay').click(function() { 
                 close_modal(modal_id);
            });
            $(o.closeButton).click(function() { 
                 close_modal(modal_id);
            });
            $(modal_id).addClass('lean_box');
            var modal_width = 300; // how do I detect the width outside the dom?
            $('#lean_overlay').css({ 'display' : 'block', opacity : 0 });
            $('#lean_overlay').fadeTo(200,o.overlay);
            $(modal_id).css({ 
                'display' : 'block',
                'position' : 'fixed',
                'opacity' : 0,
                'z-index': 11000,
                'left' : 50 + '%',
                'margin-left' : -(modal_width) + 'px',
                'top' : o.top + 'px'
            });
            return this.each(function() {
        		$(modal_id).fadeTo(200,1);
                $('body').append(modal_id);
            });
			function close_modal(modal_id){
        		$('#lean_overlay').fadeOut(200, function() {
                    $(this).remove();
                });
        		$(modal_id).remove();
			}
        }
    }); 
})(jQuery);