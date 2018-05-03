# QuickCommute

I am working on a project to build an app to help commuters in cities, with multiple transit options (e.g. subway, PATH, Lyft/Uber in NYC), travel from point (a) to (b) in a faster and more efficient manner. 

The inspiration for this project comes from some recent travel in New York City. I was attempting to find the fastest method to get from Jersey City into NYC. Google Maps presented me with multiple options, such as take transit all the way from a to b, or Lyft or drive there. However, I kept wishing that I would have an option that presented an efficient way to combine the two. 

The proposed app will take two locations, and a cost cap. Using this information it will calculate the fastest transit solution from a to b, that combines all modes of transport available to the customer. While also presenting cheaper (and slower) routes, and more expensive (may not be faster in rush hour but possibly likely more comfortable) options. 

The data being used in this project comes from two separate sources,

    Google Maps API - https://developers.google.com/maps/documentation/directions/intro

    Lyft Developer API - https://developer.lyft.com/docs
