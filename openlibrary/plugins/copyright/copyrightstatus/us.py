OLDEST_PERSON_EVER = 123

def copyright_status(edition):
    pubyear = edition.publish_year
    assumptions = ["We're assuming the year of publication is %d."% pubyear]
    assumptions.append("We're assuming that the data is correct.")
    assumptions.append("We're assuming it was published.")
    assumptions.append("We're assuming it was published in the US.")
    assumptions.append("We're assuming it was published with a valid copyright notice.")

    if pubyear < 1923:
        pdyear =  pubyear + 28 + 28
    elif pubyear < 1964:
        assumptions.append("We're assuming its copyright was renewed.")
        pdyear = pubyear + 95
    elif pubyear < 1978:
        pdyear = pubyear + 95
    else:
        assumptions.append("We're assuming it wasn't published by a corporation or under a pseudonym.")
        maxauthordeath = None
        for author in edition.authors:
            if author.get('death_year'):
                if not maxauthordeath or author.death_year > maxauthordeath:
                    maxauthordeath = author.death_year
                else:
                    assumptions.append("We're assuming that the author whose death dates are missing didn't die after those whose are available.")
        if maxauthordeath:
            pdyear = maxauthordeath + 70
        else:
            assumptions.append("We're assuming that the author lived as long as the oldest person ever and published the work at birth.")
            #TODO: look for author birth years
            pdyear = pubyear + OLDEST_PERSON_EVER
    return { 'date': pdyear, 'assumptions': assumptions }
