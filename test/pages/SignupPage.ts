import { Locator, Page } from "@playwright/test";

export class SignupPage{
    page:Page
    signupLinkLocator:Locator
    emailFieldLocator:Locator
    screenNameFeldLocator:Locator
    passwordFieldLocator:Locator
    signupButton:Locator

    constructor({page}:{page:Page}){
        this.page=page
        this.signupLinkLocator=page.getByRole('link',{name:"Sign Up"})
        this.emailFieldLocator=page.getByRole('textbox',{
            name:'Email'
        })
        this.screenNameFeldLocator=page.getByRole('textbox',{
            name:"Screen Name"
        })
        this.passwordFieldLocator=page.getByText('Password',{exact:true})
        this.signupButton=page.getByRole('button',{name:'Sign Up with Email'})
    }

    async navigateToSignUp(){
        await this.signupLinkLocator.click()
    }

    async signup(email:string,screenName:string,password:string){
        await this.emailFieldLocator.fill(email)
        await this.screenNameFeldLocator.fill(screenName)
        await this.passwordFieldLocator.fill(password)
        await this.signupButton.click()
    }

}