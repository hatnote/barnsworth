
  var DEFAULT_EXPIRE = 7200000;
  var DEFAULT_THRESH = 2;
  var REFRESH_RATE = 10;
  var KEEP = 2000; // ?
  var LIST_LIMIT = 20;
  var WP_API_URL = 'https://en.wikipedia.org/w/api.php'
  var BOOTUP_API_URL = 'http://wikimedia-foundation-2.local:5000/recent/?callback=?';
  var change_templ;

  $(function() {
    $('#modal-template').hide();
    $('#expire-time').html(DEFAULT_EXPIRE / 1000)
    change_templ = $('.edit-item:first');
    $('.item-action').on('click', function(e) {
      e.preventDefault();
      
    })
  })

  function format_number(num) {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  var change = function(wid, data) {
    this.data = data;
    this.wid = wid;
    this.title = data['page_title'];
    this.user = 'User:' + data['user'];
    // parse out date
    this.date = Date.now();
    this.is_revert = function() {
      var summary = data['summary'] ? data['summary'].toLowerCase() : '';
      if (summary.indexOf('revert') > -1) {
        return true;
      }
      if (summary.indexOf('undo') > -1) {
        return true;
      }
      if (summary.indexOf('undid') > -1) {
        return true;
      }
      if (summary.indexOf('rv ') == 0) {
        return true;
      }
      return false
    }
    if ('recv_time' in data) {
      var epoch_temp = new Date(0);
      this.date = epoch_temp.setUTCSeconds(data['recv_time']);
    } 
    this.age = function() {
      return Date.now() - this.date;
    }

    this.decayed = function() {
      var decay = (DEFAULT_EXPIRE - this.age()) / DEFAULT_EXPIRE;
      if (decay <= 0) {
        return 0
      } else {
        return decay
      }
    }

    this.expired = function(expire) {
      expire = typeof expire !== 'undefined' ? expire : DEFAULT_EXPIRE;
      if (this.age() > expire) {
        return true;
      }
      return false;
    }

  }

  function modal_click(d) {
    var url = WP_API_URL;
    var params = {
      'action': 'query',
      'list': 'users',
      'ususers': d['username'].replace('User:', ''),
      'usprop': 'editcount|registration',
      'format': 'json',
      'cmlimit': 100
    }

    var cur_item = d3.select(this.parentNode);
    var modal = $('#modal-template').clone();
    var title_list = $.map(d['edits']
      .slice(d['edits'].length - 3), function(e) { 
        return '<li><a href="' + e['data']['url'] + '" target="_blank">' + e['title'] + '</a> (' + e['data']['change_size'] + ')</li>';
      }).join('\n');
    // 
    modal.find('h2')
      .text(d['username'].replace('User:', ''));
    modal.find('.username:first')
      .text(d['username'].replace('User:', ''))
      .parent()
      .attr('href', 'https://en.wikipedia.org/wiki/' + d['username']);
    modal.find('.count:first')
      .text(d['edits'].length);
    modal.find('.recent-list:first')
      .html('<ul>' + title_list + '</ul>');
    console.log(d)
    if (!d['edits'][0]['data']['is_anon']) {
      $.ajax({
        dataType: 'jsonp',
        url: url,
        data: params,
      }).done(function(resp) {
        var user_info = resp['query']['users'][0];
        if (user_info['name'] != d['username'].replace('User:', '')) {
          console.log('Error, non-matching user info: ', user_info);
          return;
        }
        modal.find('.edit-count:first')
          .text(format_number(user_info['editcount']));
        modal.find('.join-date:first')
          .text(new Date(user_info['registration']).toDateString());
      });
    } else {
      modal.find('.edit-count:first').parents('li').remove();
      modal.find('.join-date:first')
        .parents('li')
        .remove();
      modal.find('ul:first')
        .append('<li>This is an unregistered user. Remember, <a href="https://en.wikipedia.org/wiki/Wikipedia:IPs_are_people_too" target="_blank">IPs are human too</a>!</li>');
    }
    modal
      .leanModal();
  }

  function update(data) {
    data = data.slice(0, LIST_LIMIT);
    var edit_item = d3.select('#edits').selectAll('div.item')
      .data(data, function(d) {
        if (d) {
          return [d['username'], d['score']];
        }
        return d;
      });

    edit_item
      .order()
      .each(function(d, i) {
        var cur_item = d3.select(this);
        var num = d['edits'].length;
        cur_item.select('a.last-edit')
          .attr('href', 'https://' + d['edits'][num - 1].wid + '.wikipedia.org/wiki/' + d['edits'][num - 1].title)
          .text(d['edits'][num - 1].title);
        cur_item.select('span.count').html(num);
        cur_item.select('li.score').html(d['score'])
        cur_item.select('.item_click')
          .on('click', modal_click);
      })
    item_enter = edit_item
      .order()
      .enter()
      .append('div')
      .attr('class', 'item');
    item_enter
      .append('p')
      .attr('class', 'item-user')
      .text(function(d) {
        return  d['username'].replace('User:', '');
      });
    item_enter
      .append('p')
      .attr('class', 'item-action')
      .text(function(d) {
        return 'Give barnstar';
      })
      .on('click', modal_click);
    item_enter
      .append('div')
      .attr('class', 'item-stats')
      .each(function(d) {
        var cur_item = d3.select(this);
        var num = d['edits'].length;
        var last_edit = d['edits'][num - 1];
        var wid = d['edits'][num - 1].wid;
        stats_list = cur_item.append('ul');
        stats_list
          .append('li')
          .html('Recently edited <a class="last-edit" href="https://' + wid + '.wikipedia.org/wiki/' + last_edit.title + '">' + last_edit.title + '</a>.');
        stats_list
          .append('li')
          .html('<span class="count">' + num + '</span> recent edits</li>');
        stats_list
          .append('li')
          .attr('class', 'score')
          .html('Score: ' + d['score']);
        stats_list
          .append('li')
          .html('Size: ' + d['size'] + ' (' + d['size_rel'] + ')');
        stats_list
          .append('li')
          .html('Minor edits: ' + d['minor_edits']);
        stats_list
          .append('li')
          .html('New edits: ' + d['new_edits']);
        stats_list
          .append('li')
          .html('Reverts: ' + d['reverts']);
      });
    edit_item.exit()
      .transition()
      .remove();
  }


  var recent_changes = function() {
    this.active = [];
    this.expired = [];
    this.groups = {
      'by_title': {},
      'by_user': {}
    }
    this.interesting = {
      'by_title': [],
      'by_user': []
    };
    this.total_counter = 0;

    this.add = function(wid, data) {
      edit = new change(wid, data);
      this.active.push(edit);
      this.total_counter += 1;
    }

    this.update_groups = function() {
      // reset the counters
      this.groups = {
        'by_title': {},
        'by_user': {}
      }

      for (var i = 0; i < this.active.length; i++) {
        var cur_change = this.active[i];
        // move expired changes to this.expired
        if (cur_change.expired()) {
          this.active.splice(i, 1);
          this.expired.push(cur_change)
        } else {
          // counter by title
          if (cur_change.title in this.groups['by_title']) {
            this.groups['by_title'][cur_change.title].push(cur_change);
          } else {
            this.groups['by_title'][cur_change.title] = [cur_change]
          }
          // count changes by user
          if (cur_change.user in this.groups['by_user']) {
            this.groups['by_user'][cur_change.user].push(cur_change);
          } else {
            this.groups['by_user'][cur_change.user] = [cur_change]
          }
        }
      }
      if (this.expired > KEEP) {
          // keep these around for how long?
      }
    }

    this.get_interesting = function(threshold) {
      threshold = typeof threshold !== 'undefined' ? threshold : DEFAULT_THRESH;
      this.interesting = {
        'by_title': [],
        'by_user': []
      };

      for (var user in this.groups['by_user']) {
        if (this.groups['by_user'].hasOwnProperty(user)) {
          var cur_user = this.groups['by_user'][user];
          // calculate by threshold recent edits
          if (cur_user.length >= threshold) {
            var ret = {
              'username': user,
              'score': cur_user.reduce(function (a, b) {
                  return a + b.decayed();
                }, 0),
              'edits': cur_user,
              'size': cur_user.reduce(function (a, b) {
                var size = Math.abs(b['data']['change_size'])
                if (b['data']['ns'] != 'Main' || b.is_revert()) {
                  //only count main ns and no reverts
                  size = 0;
                }
                return a + size;
              }, 0),
              'size_rel': cur_user.reduce(function (a, b) {
                var size_rel = Math.abs(b['data']['change_size']) * b.decayed();
                if (b['data']['ns'] != 'Main' || b.is_revert()) {
                  //only count main ns and no reverts
                  size_rel = 0;
                }
                return a + size_rel;
              }, 0),
              'minor_edits': cur_user.filter(function(rev) {
                return rev['data']['is_minor'] === true;
              }).length,
              'new_edits': cur_user.filter(function(rev) {
                return rev['data']['is_bot'] === true;
              }).length,
              'reverts': cur_user.filter(function(rev) {
                return rev.is_revert();
              }).length
            }
            this.interesting['by_user'].push(ret)
          }
        }
      }
      this.interesting['by_user'].sort(function(a, b) {
        return b['score'] - a['score'];
      })
    }
    this.show_interesting = function () {
      this.get_interesting()
      return this.interesting
    }
  }

  function enWikipediaSocket() {

  };

  enWikipediaSocket.init = function() {
    if (this.connection) {
       this.connection.close();
    }

    if ('WebSocket' in window) {
      var wiki_changes = new recent_changes;
      var connection = new ReconnectingWebSocket('ws://wikimon.hatnote.com/en/');
      this.connection = connection;
      var ns_counts = {}

      $.getJSON(BOOTUP_API_URL, function(resp) {
        for(var i = 0; i < resp.length; i++) {
          if (resp[i]['ns'] !== 'Special' && !resp[i]['is_bot']) {
            wiki_changes.add('en', resp[i]);
          }
        }
        wiki_changes.update_groups();
        interesting = wiki_changes.show_interesting();
        update(interesting['by_user']);
      });
      

      connection.onopen = function() {
        console.log('Connection open!');
      };

      connection.onclose = function() {
        console.log('Connection closed ...')
      };

      connection.onerror = function(error) {
        console.log('Connection Error: ' + error);
      };

      connection.onmessage = function(resp) {
        var data = JSON.parse(resp.data);
        var interesting;
        if (data['ns'] === 'Special' || data['is_bot']) {
          return;
        }

        if (ns_counts[data.ns]) {
          ns_counts[data.ns] += 1
        } else {
          ns_counts[data.ns] = 1
        }
        wiki_changes.add('en', data);
        if (wiki_changes.total_counter % REFRESH_RATE == 0) {
          wiki_changes.update_groups();
          interesting = wiki_changes.show_interesting();
          if (interesting['by_user']) {
            update(interesting['by_user']);
          }
        }
        //var rc_str = '"<a href="' + data.url + '">' + data.page_title + '</a>" was edited by ' + data.user + ' (' + data.change_size + ')'
        //log_rc(rc_str, null)
        $('#meta-active').html(wiki_changes.active.length);
        $('#meta-total').html(wiki_changes.total_counter);
        if (interesting) {
          $('#meta-score').html(interesting['by_user'].reduce(function (a, b) {
            return a + b['score'];
          }, 0));
        }
      };
    }
  };

  enWikipediaSocket.close = function() {
    if (this.connection) {
      this.connection.close();
    }
  };
  enWikipediaSocket.init();