# Online Questions

## Aim

Allow a workshop leader to ask a question to a virtual audience like "how confident are you with Verilog" and as the audience answers, the results are visible immediately as a graph on screen.

## Description 
* Allow attendees to an online workshop answer questions quickly by:
	* scanning a qr code with their phone or clicking a link
	* the types of questions:
		* multiple choice of 5 things
		* a rating from 1 to 10
		* checkboxes
		* free text
	* as people answer, the results are visible on a dashboard that can be shared onscreen
		* a % of people who have answered and some other stats are shown
		* window to answer closes after some time
* History is stored and easily exported
* Questions can be queued via a simple interface or read in a csv/spreadsheet
* On the spur of the moment a new question can be asked

## Implementation

* Should be hosted on a digital ocean style droplet with Linux as OS
* served via nginx
* simple webpages with a simple style and very fast loading
* installable as a pip python package

## Takes inspiration from 

* Mentimeter.com
