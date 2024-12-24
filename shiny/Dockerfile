# shiny and tidyverse image, fixed version
FROM rocker/shiny-verse:4.3

# system dependencies
RUN apt-get update && \
  apt-get install -y software-properties-common curl && \
  apt-get install -y --no-install-recommends \
  libssl-dev \
	libsasl2-dev \
	libcurl4-openssl-dev \
	libxml2-dev \
	cmake \
	gnupg \
	git \
	libgit2-dev \
	libudunits2-dev \
	libfontconfig1-dev \
	libcairo2-dev

# install R packages from packagemanger.rstudio (fixed versions)
RUN R -e 'install.packages(c(\
              "Rcpp",\
              "callr",\
              "shiny",\
              "shinyjs",\
              "shinymanager",\
              "shinydashboard",\
              "shinydashboardPlus",\ 
              "waiter",\ 
              "htmltools",\
              "DT",\
              "RColorBrewer",\
              "RCurl",\
              "jsonlite",\
              "fontawesome"\
            ), \
            repos="https://packagemanager.rstudio.com/cran/__linux__/focal/2024-09-09",\
            dependencies=TRUE\
          )'

# install packages from github
RUN R -e ' remotes::install_github(c(\
              "nik01010/dashboardthemes",\
              "daattali/shinyalert",\
              "daattali/shinydisconnect",\
              "daattali/shinybrowser" \
            ), \
            dependencies=TRUE\
          )'

# copy the app directory into the image
COPY . /srv/shiny-server/radian

# run app
CMD ["/usr/bin/shiny-server"]
